import torch
import torch.nn as nn
import argparse
from crnn import CRNN
from utils.loggers.log import *
from train_batch import train_batch
from utils.aftertreatment import StrLabelConverter
from utils.datasets import get_DataLoader
import time
import tqdm
from utils.fileoperation import get_chinese
from val import val
from test import test
import wandb
wandb.login(key='d58cafb4b2c769d493fb825c2d06d13a80f9ff0c')
wandb.init(project="my-test-project", entity="bowell")
wandb.config = {
  "learning_rate": 0.001,
  "epochs": 5,
  "batch_size": 16
}




def train(opt):
    if not os.path.exists(opt.name):
        os.makedirs(opt.name)
    chinese = get_chinese(opt.chinese)
    converter = StrLabelConverter(chinese)
    nclass = len(chinese) + 1
    best_model = {}
    best = opt.best

    # 训练集
    train_loader = get_DataLoader('train', opt)
    # 验证集
    val_loader = get_DataLoader('val', opt)
    criterion = nn.CTCLoss(reduction='sum')
    crnn = CRNN(opt.imgH, opt.nc, nclass, opt.nh)

    if os.path.exists(opt.weights):
        crnn.load_state_dict(torch.load(opt.weights))
    log_load_model(opt.weights)

    optimizer = torch.optim.Adam(crnn.parameters(), lr=opt.lr)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    crnn = crnn.to(device)
    criterion = criterion.to(device)

    log_parameter(opt, device)
    log_optimizer(optimizer)
    log_model(crnn)

    s_time = time.time()
    for epoch in range(1, opt.epochs + 1):
        train_iter = iter(train_loader)
        val_iter = iter(val_loader)
        total_loss = 0.
        total_num = 0.
        total_acc = 0.

        with tqdm.tqdm(range(len(train_iter))) as tbar:
            for i in tbar:
                crnn.train()
                train_loss, train_size, acc_num = train_batch(crnn, train_iter, optimizer, criterion, device, converter)

                total_loss += train_loss
                total_num += train_size
                total_acc += acc_num

                tbar.set_description('epoch {}'.format(epoch))
                tbar.set_postfix(loss=train_loss / train_size, acc=acc_num / train_size)
                tbar.update()
                wandb.log({"total_loss": total_loss,
                           'train_loss': train_loss,
                           # 'val_loss': val_loss,
                           # 'val_acc': val_acc,
                           'train_acc': total_acc,
                           'epochs': epoch})

        log_epoch(epoch, total_loss / total_num, total_acc / total_num, 'train')

        if epoch % opt.val_epoch == 0:
            val_loss, val_acc = val(crnn, val_iter, criterion, device, converter, epoch)
            if opt.save_all:
                torch.save(crnn.state_dict(),
                           'weights/chinese_' + str(epoch) + '_' + str(val_loss) + '_' + str(val_acc) + '.pt')
                log_save_model(epoch, val_loss, val_acc)

            elif val_acc > opt.best:
                opt.best = val_acc
                best_model['epoch'] = epoch
                best_model['val_loss'] = val_loss
                best_model['val_acc'] = val_acc

            if epoch == opt.epochs and not opt.save_all:
                torch.save(crnn.state_dict(),
                           'weights/last_' + str(epoch) + '_' + str(val_loss) + '_' + str(val_acc) + '.pt')
                log_save_model(epoch, val_loss, val_acc, 'last')

    if not opt.save_all and opt.best != best:
        torch.save(crnn.state_dict(),
                   'weights/best_' + str(best_model['epoch']) + '_' + str(best_model['val_loss']) + '_' +
                   str(best_model['val_acc']) + '.pt')
        log_save_model(best_model['epoch'], best_model['val_loss'], best_model['val_acc'], 'best')

    e_time = time.time()
    print('cost time:', round((e_time - s_time) / 3600., 2))

    if opt.test:
        if not opt.save_all:
            crnn = crnn.load_state_dict(
                torch.load('weights/best_' + str(best_model['epoch']) + '_' + str(best_model['val_loss']) + '_' +
                           str(best_model['val_acc']) + '.pt'))
        test_loader = get_DataLoader('test', opt)
        test_iter = iter(test_loader)
        test(crnn, test_iter, criterion, device, converter, opt.all)

    # wandb.log({"loss": wandb.plot.line_series(
    #     xs=wandb.config.epochs,
    #     ys=[train_loss, val_loss],
    #     keys=["Loss of training", "Loss of validation"],
    #     title="Loss function",
    #     xname="epochs")})
    # wandb.log({"acc": wandb.plot.line_series(
    #     xs=wandb.config.epochs,
    #     ys=[train_acc, val_acc],
    #     keys=["Accuracy of training", "Accuracy of validation"],
    #     title="Accuracy",
    #     xname="epochs")})



def parse_opt():
    parser = argparse.ArgumentParser(description='train')
    parser.add_argument('--epochs', type=int, default=20, help='训练多少轮')
    parser.add_argument('--batch_size', type=int, default=16, help='批次大小')
    parser.add_argument('--lr', type=float, default=0.001, help='学习率')
    parser.add_argument('--chinese', type=str, default='C:/Users/Bowell/Desktop/DEEPLEARNING/data2(1)/Desktop/crnn-master/data/chinese.txt', help='字符集保存路径')
    parser.add_argument('--images', type=str, default='C:/Users/Bowell/Desktop/DEEPLEARNING/data2(1)/Desktop/crnn-master/data/images/')
    parser.add_argument('--labels', type=str, default='C:/Users/Bowell/Desktop/DEEPLEARNING/data2(1)/Desktop/crnn-master/data/labels/', help='标签的路径')
    parser.add_argument('--imgH', type=int, default=32)
    parser.add_argument('--nc', type=int, default=1)
    parser.add_argument('--nh', type=int, default=256)
    parser.add_argument('--val_epoch', type=int, default=5, help='经过多少个epoch验证一次')
    parser.add_argument('--save_all', action='store_true', default=False, help='是否保存所有模型')
    parser.add_argument('--best', type=float, default=0.5, help='如果不保存所有模型，他就之会保存最好的和最后的模型，最好的模型准确率必须高于best才会保存')
    parser.add_argument('--test', action='store_true', default=True, help='模型训练好是否测试')
    parser.add_argument('--all', action='store_true', default=True,
                        help='如果开启测试，False的话就只会输出预测错误的，True就不管预测正确还是错误，都会输出')
    parser.add_argument('--weights', type=str, default='weights/best_5_0.2261927469936164_0.9710806697108066.pt', help='如果因为种种原因导致训练停止，但保存了模型，可以从这个模型开始训练，填入模型的路径')
    parser.add_argument('--name', type=str, default='weights', help='模型保存的位置')

    opt = parser.parse_args()
    return opt


if __name__ == '__main__':
    opt = parse_opt()
    train(opt)
    # Optional

    wandb.watch(model)
