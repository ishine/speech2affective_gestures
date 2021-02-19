import argparse
import os
import random
import warnings

import matplotlib.pyplot as plt
import numpy as np
import torch

import loader
import processor

from os.path import join as j


warnings.filterwarnings('ignore')


base_path = os.path.dirname(os.path.realpath(__file__))
data_path = os.path.join(base_path, '../../data')

models_ser_path = j(base_path, 'models', 'ser')
os.makedirs(models_ser_path, exist_ok=True)

parser = argparse.ArgumentParser(description='Speech to Emotive Gestures')
parser.add_argument('--dataset-ser', type=str, default='iemocap', metavar='D-SER',
                    help='dataset to train and evaluate speech emotion recognition (default: iemocap)')
parser.add_argument('--dataset-s2eg', type=str, default='ted_db', metavar='D-S2G',
                    help='dataset to train and evaluate speech to emotive gestures (default: ted)')
parser.add_argument('--frame-drop', type=int, default=2, metavar='FD',
                    help='frame down-sample rate (default: 2)')
parser.add_argument('--add-mirrored', type=bool, default=False, metavar='AM',
                    help='perform data augmentation by mirroring all the sequences (default: False)')
parser.add_argument('--train', type=bool, default=True, metavar='T',
                    help='train the model (default: True)')
parser.add_argument('--use-multiple-gpus', type=bool, default=True, metavar='T',
                    help='use multiple GPUs if available (default: True)')
parser.add_argument('--load-last-best', type=bool, default=True, metavar='LB',
                    help='load the most recent best model (default: True)')
parser.add_argument('--batch-size', type=int, default=128, metavar='B',
                    help='input batch size for training (default: 32)')
parser.add_argument('--num-worker', type=int, default=4, metavar='W',
                    help='number of threads? (default: 4)')
parser.add_argument('--start-epoch', type=int, default=20, metavar='SE',
                    help='starting epoch of training (default: 0)')
parser.add_argument('--num-epoch', type=int, default=5000, metavar='NE',
                    help='number of epochs to train (default: 1000)')
# parser.add_argument('--window-length', type=int, default=1, metavar='WL',
#                     help='max number of past time steps to take as input to transformer decoder (default: 60)')
parser.add_argument('--optimizer', type=str, default='Adam', metavar='O',
                    help='optimizer (default: Adam)')
parser.add_argument('--base-lr', type=float, default=1e-3, metavar='LR',
                    help='base learning rate (default: 1e-2)')
parser.add_argument('--base-tr', type=float, default=1., metavar='TR',
                    help='base teacher rate (default: 1.0)')
parser.add_argument('--step', type=list, default=0.05 * np.arange(20), metavar='[S]',
                    help='fraction of steps when learning rate will be decreased (default: [0.5, 0.75, 0.875])')
parser.add_argument('--lr-decay', type=float, default=0.9999, metavar='LRD',
                    help='learning rate decay (default: 0.999)')
parser.add_argument('--tf-decay', type=float, default=0.995, metavar='TFD',
                    help='teacher forcing ratio decay (default: 0.995)')
parser.add_argument('--gradient-clip', type=float, default=0.1, metavar='GC',
                    help='gradient clip threshold (default: 0.1)')
parser.add_argument('--nesterov', action='store_true', default=True,
                    help='use nesterov')
parser.add_argument('--momentum', type=float, default=0.9, metavar='M',
                    help='momentum (default: 0.9)')
parser.add_argument('--weight-decay', type=float, default=5e-4, metavar='D',
                    help='Weight decay (default: 5e-4)')
parser.add_argument('--upper-body-weight', type=float, default=1., metavar='UBW',
                    help='loss weight on the upper body joint motions (default: 2.05)')
parser.add_argument('--affs-reg', type=float, default=0.8, metavar='AR',
                    help='regularization for affective features loss (default: 0.01)')
parser.add_argument('--quat-norm-reg', type=float, default=0.1, metavar='QNR',
                    help='regularization for unit norm constraint (default: 0.01)')
parser.add_argument('--quat-reg', type=float, default=1.2, metavar='QR',
                    help='regularization for quaternion loss (default: 0.01)')
parser.add_argument('--recons-reg', type=float, default=1.2, metavar='RCR',
                    help='regularization for reconstruction loss (default: 1.2)')
parser.add_argument('--eval-interval', type=int, default=1, metavar='EI',
                    help='interval after which model is evaluated (default: 1)')
parser.add_argument('--log-interval', type=int, default=100, metavar='LI',
                    help='interval after which log is printed (default: 100)')
parser.add_argument('--save-interval', type=int, default=10, metavar='SI',
                    help='interval after which model is saved (default: 10)')
parser.add_argument('--no-cuda', action='store_true', default=False,
                    help='disables CUDA training')
parser.add_argument('--pavi-log', action='store_true', default=False,
                    help='pavi log')
parser.add_argument('--print-log', action='store_true', default=True,
                    help='print log')
parser.add_argument('--save-log', action='store_true', default=True,
                    help='save log')
# TO ADD: save_result

args = parser.parse_args()
randomized = False

args.work_dir_ser = os.path.join(models_ser_path, args.dataset_ser)
os.makedirs(args.work_dir_ser, exist_ok=True)

# train_data_wav, eval_data_wav, test_data_wav,\
#     train_labels_dim, eval_labels_dim, test_labels_dim,\
#     means, stds = loader.load_ted_db_data(data_path, args.dataset_s2eg)

train_data_wav, eval_data_wav, test_data_wav, \
    train_labels_cat, eval_labels_cat, test_labels_cat, \
    train_labels_dim, eval_labels_dim, test_labels_dim, \
    means, stds = loader.load_iemocap_data(data_path, args.dataset_ser)

_, wav_channels, wav_height, wav_width = train_data_wav.shape
num_emo_cats = train_labels_cat.shape[-1]
num_emo_dims = train_labels_dim.shape[-1]

data_loader = dict(train_data=train_data_wav, train_labels_cat=train_labels_cat, train_labels_dim=train_labels_dim,
                   eval_data=eval_data_wav, eval_labels_cat=eval_labels_cat, eval_labels_dim=eval_labels_dim,
                   test_data=test_data_wav, test_labels_cat=test_labels_cat, test_labels_dim=test_labels_dim,)

pr = processor.Processor(args, data_path, data_loader,
                         wav_channels, wav_height, wav_width,
                         num_emo_cats, num_emo_dims,
                         save_path=base_path)

if args.train:
    pr.train()

pr.generate_motion(samples_to_generate=len(data_loader['test']), randomized=randomized)