'''
mnist_gan.py

Trains a GAN model on the MNIST database.
'''

import os # path manipulation and OS resources
import time # Time measurement
import yaml # Open configuration file
import shutil # To copy/move files
import models as models # Custom GAN models
import matplotlib.pyplot as plt # plots
import torch # Torch variables handler
import torch.nn as nn # Networks support
import torch.nn.functional as F # functional
import torch.nn.parallel # parallel support
import torch.backends.cudnn as cudnn # Cuda support
import torch.optim as optim # Optimizer
import torchvision.transforms as tf # Data transforms
import torch.utils.data as data # Data loaders
import torchvision.utils as vutils # Image utils
from utils.meter import AverageMeter # measurement
from utils.data import ConcDataset # Data set concatenation
from torchvision.datasets import MNIST # Datasets

def checkpoint(state, is_best, curpath, bstpath):
    '''
    Saves current model.

    @param state Current model state.
    @param is_best Boleean flag testing if current models is the best model.
    @param curpath Current model file output path.
    @param bstpath Best model file output path.
    '''

    # Save current and best model
    torch.save(state, curpath)
    if is_best:
        shutil.copy(curpath, bstpath)


def train(dload, dmodel, gmodel, dopt, gopt, conf, zt, rslt_path):
    '''
    Trains the models.

    @param dload Data loader.
    @param dmodel Discriminator.
    @parma gmodel Generator.
    @param dopt Discriminator optimizer.
    @param gopt Generator optimizer.
    @param conf configuration data.
    @param zt test figure noise
    @param rslt_path Resulting images path.

    @return discriminator and generator losses.
    '''

    # Average meters
    tbatch = AverageMeter() # Batch time
    tdload = AverageMeter() # Loading time
    avgdlss = AverageMeter() # Average discriminator loss
    avgglss = AverageMeter() # Average generator loss

    # Switch models to training mode
    dmodel.train()
    gmodel.train()

    # Configuration info
    zindim = conf['zindim']

    # Compute batch evaluation
    end_time = time.time()
    for i, (imgs, _) in enumerate(dload):

        # Loading time
        tdload.update(time.time() - end_time)

        # Setting labels
        btsize = imgs.size(0)
        real_label = torch.autograd.Variable(torch.ones((btsize,1)).cuda())
        fake_label = torch.autograd.Variable(torch.zeros((btsize,1)).cuda())

        # Set variables
        zdim = [btsize, zindim]
        imgs_var = torch.autograd.Variable(imgs.cuda())
        zvec_var = torch.randn(zdim)
        zvec_var = torch.autograd.Variable(zvec_var.cuda())

        # Computing generator images
        fake = gmodel(zvec_var)

        # Computing discriminator error
        dlss = F.binary_cross_entropy(dmodel(imgs_var), real_label)
        dlss += F.binary_cross_entropy(dmodel(fake.detach()), fake_label)

        # Update the discriminator
        dopt.zero_grad()
        dlss.backward()
        dopt.step()

        # Generate new images
        zvec_var = torch.randn(zdim)
        zvec_var = torch.autograd.Variable(zvec_var.cuda())
        fake = gmodel(zvec_var)

        # Update the generator error
        glss = F.binary_cross_entropy(dmodel(fake), real_label)
        gopt.zero_grad()
        glss.backward()
        gopt.step()

        # Measure losses
        avgdlss.update(dlss.data[0], btsize)
        avgglss.update(glss.data[0], btsize)

        # Measure batch time
        tbatch.update(time.time() - end_time)

        # Print info
        print('Epoch: [{0}][{1}/{2}]\t'
            'Time {tbatch.val:.3f} ({tbatch.avg:.3f})\t'
            'Data {tdload.val:.3f} ({tdload.avg:.3f})\t'
            'DLoss {avgdlss.val:.4f} ({avgdlss.avg:.4f})\t'
            'GLoss {avgglss.val:.4f} ({avgglss.avg:.4f})\t'.format(
                epoch, i, len(dload), tbatch=tbatch, tdload=tdload,
                avgdlss=avgdlss, avgglss=avgglss
            )
        )

        # Print images
        if i % 100 == 0:
            vutils.save_image(imgs, rslt_path+'real.png',\
            normalize=True, nrow=16)
            out = gmodel(zt)
            vutils.save_image(out.data, rslt_path+'fake.png',\
            normalize=True, nrow=16)

        # Reset time
        end_time = time.time()

    # Return losses
    return avgdlss.avg, avgglss.avg

if __name__ == '__main__':

    # Config path
    data_path = '../data/mnist/'
    conf_path = '../conf/mnist_gf2014.yaml'
    rslt_path = '../rslt/mnist/'

    # Open config file
    conf = None
    with open(conf_path, 'r') as cf:
        conf = yaml.load(cf)

    # Setting outputs
    cur_mdl_pth = rslt_path+'cgan_curr.pth.tar'
    bst_mdl_pth = rslt_path+'cgan_best.pth.tar'
    imgs_path = rslt_path+conf['dmodel']+'_'+conf['gmodel']+'.pdf'

    # Setting initial losses
    conf['cepoch'] = 0
    conf['dmloss'], conf['gmloss'], conf['smloss'] = [], [], []
    min_lss = float('inf')

    # Load MNIST dataset
    norms = tf.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]) # Normalize
    totns = tf.ToTensor() # Converts to tensor
    mnist_trset = MNIST(data_path, True, tf.Compose([totns, norms]))
    mnist_tsset = MNIST(data_path, False, tf.Compose([totns, norms]))
    mnist_set = ConcDataset([mnist_trset, mnist_tsset])

    # Setting loader
    btsize, nworks = conf['btsize'], conf['nworks']
    dload = data.DataLoader(mnist_set, btsize, True, None, nworks)

    # Setting models
    imsz, dlyrs, glyrs = tuple(conf['imsize']), conf['dlayer'], conf['glayer']
    dmodel = models.__dict__[conf['dmodel']](dlyrs, imsz)
    gmodel = models.__dict__[conf['gmodel']](glyrs, imsz)

    # Setting to parallel
    dmodel = torch.nn.DataParallel(dmodel).cuda()
    gmodel = torch.nn.DataParallel(gmodel).cuda()
    cudnn.benchmark = True # Inbuilt cudnn auto-tuner (fastest)

    # Loading models
    if os.path.isfile(cur_mdl_pth):
        check = torch.load(cur_mdl_pth)
        dmodel.load_state_dict(check['dmodel'])
        gmodel.load_state_dict(check['gmodel'])
        conf = check['conf']

    # Setting optimizers
    lr, mm = conf['learnr'], conf['momntm']
    dopt = optim.Adam(dmodel.parameters(), lr=lr)
    gopt = optim.Adam(gmodel.parameters(), lr=lr)

    # Auxiliary random fixed noise
    zt = torch.randn(btsize, glyrs[0])
    zt = torch.autograd.Variable(zt.cuda())

    # Training loop
    for epoch in range(conf['cepoch'], conf['nepoch']):

        # Train model
        dmloss, gmloss = train(dload,dmodel,gmodel,dopt,gopt,conf,zt,rslt_path)

        # Update losses
        conf['dmloss'].append(dmloss)
        conf['gmloss'].append(gmloss)
        conf['smloss'].append(dmloss+gmloss)
        conf['cepoch'] = epoch+1

        # Set checkpoint
        check = {'dmodel': dmodel.state_dict(), 'gmodel': gmodel.state_dict()}
        check['conf'] = conf

        # Save model
        is_best = conf['smloss'][-1] < min_lss
        min_lss = min(conf['smloss'][-1], min_lss)
        checkpoint(check, is_best, cur_mdl_pth, bst_mdl_pth)

        # Plot
        plt.rc('text', usetex=True)
        plt.rc('font', family='serif')
        plt.figure(figsize=(11.69,8.27))

        # Plot
        plt.plot(conf['smloss'], 'k.-', label='Sum')
        plt.plot(conf['dmloss'], 'ro-.', label='D')
        plt.plot(conf['gmloss'], 'g--^', label='G')
        plt.legend(loc='best')
        plt.ylabel('Loss')
        plt.xlabel('Epoch')

        # Save
        plt.savefig(imgs_path)
        plt.close('all')
