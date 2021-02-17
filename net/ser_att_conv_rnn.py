import torch
import torch.nn as nn
from torch.nn import GRU


def truncate_param(param, value):
    param_copy = param.clone()
    param_copy[torch.abs(param_copy) >= value] = 0.
    return param_copy


class Attention(nn.Module):
    def __init__(self, hidden_size, attention_size, bidirectional):
        super(Attention, self).__init__()

        if bidirectional:
            hidden_size *= 2
        self.linear1 = nn.Linear(hidden_size, attention_size)
        nn.init.normal(self.linear1.weight, std=0.1)
        nn.init.constant(self.linear1.bias, 0.1)
        self.linear2 = nn.Linear(attention_size, 1)
        nn.init.normal(self.linear2.weight, std=0.1)
        nn.init.constant(self.linear2.bias, 0.1)

    def forward(self, x):
        v = torch.sigmoid(self.linear1(x))
        alphas = torch.softmax(self.linear2(v), dim=-2)
        output = torch.sum(x * alphas, dim=1)
        return output, alphas


class AttConvRNN(nn.Module):
    def __init__(self, C, H, W, D, L1=5, L2=7,
                 gru_cell_units=128,
                 attention_size=1,
                 num_linear=768,
                 pool_stride_height=2,
                 pool_stride_width=4,
                 F1=64,
                 bidirectional=True,
                 dropout_keep_prob=1,
                 init_std=0.1,
                 init_const=0.1):
        super(AttConvRNN, self).__init__()

        self.conv1 = nn.Conv2d(C, L1, (5, 3), padding=(2, 1))
        nn.init.normal(self.conv1.weight, std=init_std)
        self.conv1.weight.data = truncate_param(self.conv1.weight, init_std * 2.)
        nn.init.constant(self.conv1.bias, init_const)
        self.max_pool1 = nn.MaxPool2d((pool_stride_height, pool_stride_width),
                                      stride=(pool_stride_height, pool_stride_width))

        self.conv2 = nn.Conv2d(L1, L2, (5, 3), padding=(2, 1))
        nn.init.normal(self.conv2.weight, std=init_std)
        self.conv2.weight.data = truncate_param(self.conv2.weight, init_std * 2.)
        nn.init.constant(self.conv2.bias, init_const)
        self.conv3 = nn.Conv2d(L2, L2, (5, 3), padding=(2, 1))
        nn.init.normal(self.conv3.weight, std=init_std)
        self.conv3.weight.data = truncate_param(self.conv3.weight, init_std * 2.)
        nn.init.constant(self.conv3.bias, init_const)
        self.conv4 = nn.Conv2d(L2, L2, (5, 3), padding=(2, 1))
        nn.init.normal(self.conv4.weight, std=init_std)
        self.conv4.weight.data = truncate_param(self.conv4.weight, init_std * 2.)
        nn.init.constant(self.conv4.bias, init_const)
        self.conv5 = nn.Conv2d(L2, L2, (5, 3), padding=(2, 1))
        nn.init.normal(self.conv5.weight, std=init_std)
        self.conv5.weight.data = truncate_param(self.conv5.weight, init_std * 2.)
        nn.init.constant(self.conv5.bias, init_const)
        self.conv6 = nn.Conv2d(L2, L2, (5, 3), padding=(2, 1))
        nn.init.normal(self.conv6.weight, std=init_std)
        self.conv6.weight.data = truncate_param(self.conv6.weight, init_std * 2.)
        nn.init.constant(self.conv6.bias, init_const)

        self.linear1 = nn.Linear(L2 * W // pool_stride_width,
                                 num_linear)
        nn.init.normal(self.linear1.weight, std=init_std)
        self.linear1.weight.data = truncate_param(self.linear1.weight, init_std * 2.)
        nn.init.constant(self.linear1.bias, init_const)

        self.gru = nn.GRU(num_linear, gru_cell_units, batch_first=True, bidirectional=bidirectional)
        bias_len = len(self.gru.bias_hh_l0)
        nn.init.constant(self.gru.bias_hh_l0[bias_len // 4:bias_len // 2], 1.)
        nn.init.constant(self.gru.bias_hh_l0_reverse[bias_len // 4:bias_len // 2], 1.)
        nn.init.constant(self.gru.bias_ih_l0[bias_len // 4:bias_len // 2], 1.)
        nn.init.constant(self.gru.bias_ih_l0_reverse[bias_len // 4:bias_len // 2], 1.)
        self.attention = Attention(gru_cell_units, attention_size=attention_size, bidirectional=bidirectional)

        self.linear2 = nn.Linear(gru_cell_units * 2 if bidirectional else 1, F1)
        nn.init.normal(self.linear2.weight, std=init_std)
        self.linear2.weight.data = truncate_param(self.linear2.weight, init_std * 2.)
        nn.init.constant(self.linear2.bias, init_const)
        self.linear3 = nn.Linear(F1, D)
        nn.init.normal(self.linear3.weight, std=init_std)
        self.linear3.weight.data = truncate_param(self.linear3.weight, init_std * 2.)
        nn.init.constant(self.linear3.bias, init_const)

        self.leaky_relu = nn.LeakyReLU(1e-2)

    def forward(self, x):
        x_01 = self.leaky_relu(self.conv1(x))
        x_02 = self.max_pool1(x_01)
        x_03 = self.leaky_relu(self.conv2(x_02))
        x_04 = self.leaky_relu(self.conv3(x_03))
        x_05 = self.leaky_relu(self.conv4(x_04))
        x_06 = self.leaky_relu(self.conv5(x_05))
        x_07 = self.leaky_relu(self.conv6(x_06)).permute(0, 2, 1, 3)
        x_08 = self.leaky_relu(self.linear1(x_07.contiguous().view(x_07.shape[0], x_07.shape[1], -1)))
        x_09, _ = self.gru(x_08)
        x_10, alphas = self.attention(x_09)
        x_11 = self.leaky_relu(self.linear2(x_10))
        x_12 = torch.clamp(self.linear3(x_11), -3., 3.)

        # if torch.max(x_12[0] - x_12[1]) < 1e-3 and torch.min(x_12[0] - x_12[1]) < 1e-3:
        #     stop

        return x_12
