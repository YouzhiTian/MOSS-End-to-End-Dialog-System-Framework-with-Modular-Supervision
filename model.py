import torch
import random
import numpy as np
from config import global_config as cfg
from reader import CamRest676Reader, get_glove_matrix
from reader import KvretReader
from tsd_net import TSD, cuda_, nan
from torch.optim import Adam, RMSprop
from torch.autograd import Variable
from reader import pad_sequences
import argparse, time

from metric import CamRestEvaluator, KvretEvaluator
import logging


class Model:
    def __init__(self, dataset):
        reader_dict = {
            'camrest': CamRest676Reader,
            'kvret': KvretReader,
        }
        model_dict = {
            'TSD':TSD
        }
        evaluator_dict = {
            'camrest': CamRestEvaluator,
            'kvret': KvretEvaluator,
        }
        self.reader = reader_dict[dataset]()
        self.m = model_dict[cfg.m](embed_size=cfg.embedding_size,
                               hidden_size=cfg.hidden_size,
                               vocab_size=cfg.vocab_size,
                               layer_num=cfg.layer_num,
                               dropout_rate=cfg.dropout_rate,
                               z_length=cfg.z_length,
                               max_ts=cfg.max_ts,
                               beam_search=cfg.beam_search,
                               beam_size=cfg.beam_size,
                               eos_token_idx=self.reader.vocab.encode('EOS_M'),
                               vocab=self.reader.vocab,
                               teacher_force=cfg.teacher_force,
                               degree_size=cfg.degree_size,
                               reader=self.reader)
        self.EV = evaluator_dict[dataset] # evaluator class
        if cfg.cuda: self.m = self.m.cuda()
        self.optim = Adam(lr=cfg.lr, params=filter(lambda x: x.requires_grad, self.m.parameters()),weight_decay=5e-5)
        self.base_epoch = -1

    def _convert_batch(self, py_batch, prev_z_py=None,prev_z1_py=None,prev_z2_py=None,prev_z3_py=None):
        
        if prev_z_py is None:
            prev_z_py = [[self.reader.vocab.encode('EOS_Z1'),self.reader.vocab.encode('EOS_Z2')]] * len(py_batch['bspan']) #  this is the bspan of all. 
            #print(turn_batch['bspan'])
            #print(prev_z)
        if prev_z1_py is None:
            prev_z1_py = [[self.reader.vocab.encode('EOS_Z1')]] * len(py_batch['constraint'])
        if prev_z2_py is None:
            prev_z2_py = [[self.reader.vocab.encode('EOS_Z2')]]*len(py_batch['user_tag'])
        if prev_z3_py is None:
            prev_z3_py = [[self.reader.vocab.encode('<split>')]]* len(py_batch['system'])

        
        
        u_input_py = py_batch['user']
        u_len_py = py_batch['u_len']
        kw_ret = {}
       
        for i in range(len(prev_z_py)):
            eob = self.reader.vocab.encode('EOS_Z2')
            if eob in prev_z_py[i] and prev_z_py[i].index(eob) != len(prev_z_py[i]) - 1:
                idx = prev_z_py[i].index(eob)
                prev_z_py[i] = prev_z_py[i][:idx + 1]
            for j, word in enumerate(prev_z_py[i]):
                if word >= cfg.vocab_size:
                    prev_z_py[i][j] = 2 #unk
        for i in range(len(prev_z1_py)):
            eob = self.reader.vocab.encode('EOS_Z1')
            if eob in prev_z1_py[i] and prev_z1_py[i].index(eob) != len(prev_z1_py[i]) - 1:
                idx = prev_z1_py[i].index(eob)
                prev_z1_py[i] = prev_z1_py[i][:idx + 1]
            
        for i in range(len(prev_z2_py)):
            eob = self.reader.vocab.encode('EOS_Z2')
            if eob in prev_z2_py[i] and prev_z2_py[i].index(eob) != len(prev_z2_py[i]) - 1:
                idx = prev_z2_py[i].index(eob)
                prev_z2_py[i] = prev_z2_py[i][:idx + 1]
            
        for i in range(len(prev_z3_py)):
            eob = self.reader.vocab.encode('<split>')
            if eob in prev_z3_py[i] and prev_z3_py[i].index(eob) != len(prev_z3_py[i]) - 1:
                idx = prev_z3_py[i].index(eob)
                prev_z3_py[i] = prev_z3_py[i][:idx + 1]    



        prev_z_input_np = pad_sequences(prev_z_py, cfg.max_ts, padding='post', truncating='pre').transpose((1, 0))
        prev_z_len = np.array([len(_) for _ in prev_z_py])
        prev_z_input = cuda_(Variable(torch.from_numpy(prev_z_input_np).long()))
        kw_ret['prev_z_len'] = prev_z_len
        kw_ret['prev_z_input'] = prev_z_input
        kw_ret['prev_z_input_np'] = prev_z_input_np



        prev_z1_input_np = pad_sequences(prev_z1_py, cfg.max_ts, padding='post', truncating='pre').transpose((1, 0))
        prev_z1_len = np.array([len(_) for _ in prev_z1_py])
        prev_z1_input = cuda_(Variable(torch.from_numpy(prev_z1_input_np).long()))
        kw_ret['prev_z1_len'] = prev_z1_len
        kw_ret['prev_z1_input'] = prev_z1_input
        kw_ret['prev_z1_input_np'] = prev_z1_input_np

        prev_z2_input_np = pad_sequences(prev_z2_py, cfg.max_ts, padding='post', truncating='pre').transpose((1, 0))
        prev_z2_len = np.array([len(_) for _ in prev_z2_py])
        prev_z2_input = cuda_(Variable(torch.from_numpy(prev_z2_input_np).long()))
        kw_ret['prev_z2_len'] = prev_z2_len
        kw_ret['prev_z2_input'] = prev_z2_input
        kw_ret['prev_z2_input_np'] = prev_z2_input_np

        prev_z3_input_np = pad_sequences(prev_z3_py, cfg.max_ts, padding='post', truncating='pre').transpose((1, 0))
        prev_z3_len = np.array([len(_) for _ in prev_z3_py])
        prev_z3_input = cuda_(Variable(torch.from_numpy(prev_z3_input_np).long()))
        kw_ret['prev_z3_len'] = prev_z3_len
        kw_ret['prev_z3_input'] = prev_z3_input
        kw_ret['prev_z3_input_np'] = prev_z3_input_np

        degree_input_np = np.array(py_batch['degree'])
        u_input_np = pad_sequences(u_input_py, cfg.max_ts, padding='post', truncating='pre').transpose((1, 0))

        z_input_np = pad_sequences(py_batch['bspan'], padding='post').transpose((1, 0))
        # z1_input_np = pad_sequences(py_batch['constraint'], padding='post').transpose((1, 0))
        z1_input_np = pad_sequences(py_batch['bspan'], padding='post').transpose((1, 0))
        z2_input_np = pad_sequences(py_batch['user_tag'], padding='post').transpose((1, 0))
        z3_input_np = pad_sequences(py_batch['system'], padding='post').transpose((1, 0))
        m_input_np = pad_sequences(py_batch['response'], cfg.max_ts, padding='post', truncating='post').transpose(
            (1, 0))

        u_len = np.array(u_len_py)
        m_len = np.array(py_batch['m_len'])

        degree_input = cuda_(Variable(torch.from_numpy(degree_input_np).float()))
        u_input = cuda_(Variable(torch.from_numpy(u_input_np).long()))
        z_input = cuda_(Variable(torch.from_numpy(z_input_np).long()))
        z1_input = cuda_(Variable(torch.from_numpy(z1_input_np).long()))
        z2_input = cuda_(Variable(torch.from_numpy(z2_input_np).long()))
        z3_input = cuda_(Variable(torch.from_numpy(z3_input_np).long()))
        m_input = cuda_(Variable(torch.from_numpy(m_input_np).long()))

        kw_ret['z_input_np'] = z_input_np
        kw_ret['z1_input_np'] = z1_input_np
        kw_ret['z2_input_np'] = z2_input_np
        kw_ret['z3_input_np'] = z3_input_np
        kw_ret['constraint'] = py_batch['constraint'] # to do. convert list to tensor first, then to cuda. 
        kw_ret['user_tag'] = py_batch['user']
        kw_ret['system'] = py_batch['system']

        return u_input, u_input_np, z_input, z1_input,z2_input,z3_input,m_input, m_input_np,u_len, m_len,  \
               degree_input, kw_ret

    def train(self):
        lr = cfg.lr
        prev_min_loss, early_stop_count = 1 << 30, cfg.early_stop_count
        train_time = 0
        for epoch in range(cfg.epoch_num):
            sw = time.time()
            if epoch <= self.base_epoch:
                continue
            self.training_adjust(epoch)
            self.m.self_adjust(epoch)
            sup_loss = 0
            sup_cnt = 0
            data_iterator = self.reader.mini_batch_iterator('train')
            optim = self.optim
            for iter_num, dial_batch in enumerate(data_iterator):
                turn_states = {}
                prev_z = None
                prev_z1 = None
                prev_z2 = None
                prev_z3 = None
                for turn_num, turn_batch in enumerate(dial_batch):
                    if prev_z is None:
                        prev_z = [[self.reader.vocab.encode('EOS_Z1'), self.reader.vocab.encode('EOS_Z2')]] * len(turn_batch['bspan']) # : this is the bspan of all. 
                    if prev_z1 is None:
                        prev_z1 = [[self.reader.vocab.encode('EOS_Z1')]] * len(turn_batch['constraint'])
                    if prev_z2 is None:
                        prev_z2 = [[self.reader.vocab.encode('EOS_Z2')]]*len(turn_batch['user_tag'])
                    if prev_z3 is None:
                        prev_z3 = [[self.reader.vocab.encode('<split>')]]* len(turn_batch['system'])


                    if cfg.truncated:
                        logging.debug('iter %d turn %d' % (iter_num, turn_num))
                    optim.zero_grad()
                    u_input, u_input_np, z_input,z1_input,z2_input,z3_input, m_input, m_input_np, u_len, \
                    m_len, degree_input, kw_ret \
                        = self._convert_batch(turn_batch, prev_z,prev_z1,prev_z2,prev_z3)

                    loss, pr_loss,pr1_loss, pr2_loss, pr3_loss, m_loss, turn_states = self.m(u_input=u_input, z_input=z_input,z1_input=z1_input,z2_input=z2_input,z3_input=z3_input,
                                                                        m_input=m_input,
                                                                        degree_input=degree_input,
                                                                        u_input_np=u_input_np,
                                                                        m_input_np=m_input_np,
                                                                        turn_states=turn_states,
                                                                        u_len=u_len, m_len=m_len, mode='train', **kw_ret)
                    loss.backward(retain_graph=turn_num != len(dial_batch) - 1)
                    #grad = torch.nn.utils.clip_grad_norm(self.m.parameters(), 5.0)
                    grad = torch.nn.utils.clip_grad_norm_(self.m.parameters(), 5.0)
                    
                    optim.step()
                    sup_loss += loss.item()
                    sup_cnt += 1
                    logging.debug(
                        'loss:{} pr_loss:{} pr1_loss:{} pr2_loss:{} pr3_loss:{} m_loss:{} grad:{}'.format(loss.item(),
                                                                       pr_loss.item(),
                                                                       pr1_loss.item(),
                                                                       pr2_loss.item(),
                                                                       pr3_loss.item(),
                                                                       m_loss.item(),
                                                                       grad))
                    # print(
                    #     'loss:{} pr_loss:{} pr1_loss:{} pr2_loss:{} pr3_loss:{} m_loss:{} grad:{}'.format(loss.item(),
                    #                                                    pr_loss.item(),
                    #                                                    pr1_loss.item(),
                    #                                                    pr2_loss.item(),
                    #                                                    pr3_loss.item(),
                    #                                                    m_loss.item(),
                    #                                                    grad))

                    prev_z = turn_batch['bspan']

            epoch_sup_loss = sup_loss / (sup_cnt + 1e-8)
            train_time += time.time() - sw
            logging.info('Traning time: {}'.format(train_time))
            logging.info('avg training loss in epoch %d sup:%f' % (epoch, epoch_sup_loss))

            valid_sup_loss, valid_unsup_loss = self.validate()
            logging.info('validation loss in epoch %d sup:%f unsup:%f' % (epoch, valid_sup_loss, valid_unsup_loss))
            logging.info('time for epoch %d: %f' % (epoch, time.time()-sw))
            valid_loss = valid_sup_loss + valid_unsup_loss
            self.save_model(epoch)
            # if epoch !=7 and epoch !=9 and epoch != 11: #
            if valid_loss <= prev_min_loss:
                self.save_model(epoch)
                prev_min_loss = valid_loss
            else:
                early_stop_count -= 1
                lr *= cfg.lr_decay
                if not early_stop_count:
                    break
                self.optim = Adam(lr=lr, params=filter(lambda x: x.requires_grad, self.m.parameters()),
                                  weight_decay=5e-5)
                logging.info('early stop countdown %d, learning rate %f' % (early_stop_count, lr))
                
    def eval(self, data='test'):
        #print("aaaaaaaaaaaaaaaa")
        self.m.eval()
        self.reader.result_file = None
        data_iterator = self.reader.mini_batch_iterator(data)
        mode = 'test' if not cfg.pretrain else 'pretrain_test'
        for batch_num, dial_batch in enumerate(data_iterator):
            turn_states = {}
            prev_z = None
            prev_z1 = None
            prev_z2 = None
            prev_z3 = None
            for turn_num, turn_batch in enumerate(dial_batch):
                u_input, u_input_np, z_input,z1_input,z2_input,z3_input, m_input, m_input_np, u_len, \
                m_len, degree_input, kw_ret \
                    = self._convert_batch(turn_batch, prev_z,prev_z1,prev_z2,prev_z3)
                m_idx, z_idx,z1_idx, z2_idx, z3_idx, turn_states = self.m(mode=mode, u_input=u_input, u_len=u_len, z_input=z_input,z1_input=z1_input,z2_input=z2_input,z3_input=z3_input,
                                                   m_input=m_input,
                                                   degree_input=degree_input, u_input_np=u_input_np,
                                                   m_input_np=m_input_np, m_len=m_len, turn_states=turn_states,
                                                   dial_id=turn_batch['dial_id'], **kw_ret)
                self.reader.wrap_result(turn_batch, m_idx, z_idx, z1_idx, z2_idx, z3_idx, prev_z=prev_z)
                greedy = []
                i = 0
                # for i in range(len(z1_idx)):
                #     temp = []
                #     for ip in z1_idx[i]:
                #         if ip != self.reader.vocab.encode("EOS_Z1"):
                #             temp.append(ip)
                #         if ip == self.reader.vocab.encode("EOS_Z1"):
                #             break
                #     temp.append(self.reader.vocab.encode("EOS_Z1"))
                #     for ip in z2_idx[i]:
                #         if ip != self.reader.vocab.encode("EOS_Z2"):
                #             temp.append(ip)
                #         if ip == self.reader.vocab.encode("EOS_Z2"):
                #             break
                #     temp.append(self.reader.vocab.encode("EOS_Z2"))
                #     greedy.append(temp)
                greedy = z1_idx
                
                
                
                
                if cfg.eval_with_ground_truth is True:
                    # using ground truth as the B_{t-1} for evaluation.
                    # with user simulation, we should then change it to greedy approach.
                    prev_z = turn_batch['bspan'] # XXX warning: we no longer use the 
                    # previous generated bspan as the input.
                    # instead, we fetch the ground truth bspan of the prevsiou trun for evaluating the next turn. 
                else:
                    prev_z = greedy # greedy approach
        ev = self.EV(result_path=cfg.result_path)
        res = ev.run_metrics()
        self.m.train()
        return res

    def validate(self, data='dev'):
        self.m.eval()
        data_iterator = self.reader.mini_batch_iterator(data)
        sup_loss, unsup_loss = 0, 0
        sup_cnt, unsup_cnt = 0, 0
        for dial_batch in data_iterator:
            turn_states = {}
            prev_z = None
            for turn_num, turn_batch in enumerate(dial_batch):
                if prev_z is None:
                        prev_z = [[self.reader.vocab.encode('EOS_Z1'), self.reader.vocab.encode('EOS_Z2')]] * len(turn_batch['bspan']) # : this is the bspan of all. 
                    
                u_input, u_input_np, z_input,z1_input,z2_input,z3_input, m_input, m_input_np, u_len, \
                m_len, degree_input, kw_ret \
                    = self._convert_batch(turn_batch,prev_z)

                loss, pr_loss,pr1_loss, pr2_loss, pr3_loss, m_loss, turn_states = self.m(u_input=u_input, z_input=z_input,z1_input=z1_input,z2_input=z2_input,z3_input=z3_input,
                                                                    m_input=m_input,
                                                                    turn_states=turn_states,
                                                                    degree_input=degree_input,
                                                                    u_input_np=u_input_np, m_input_np=m_input_np,
                                                                    u_len=u_len, m_len=m_len, mode='train',**kw_ret)
                sup_loss += loss.item()
                sup_cnt += 1
                logging.debug(
                    'loss:{} pr_loss:{} pr1_loss:{} pr2_loss:{} pr3_loss:{} m_loss:{}'.format(loss.item(), pr_loss.item(), pr1_loss.item(), pr2_loss.item(), pr3_loss.item(), m_loss.item()))
                prev_z = turn_batch['bspan']
        sup_loss /= (sup_cnt + 1e-8)
        unsup_loss /= (unsup_cnt + 1e-8)
        self.m.train()
        print('result preview...')
        self.eval()
        return sup_loss, unsup_loss

    
    def reinforce_tune(self):
        lr = cfg.lr
        self.optim = Adam(lr=cfg.lr, params=filter(lambda x: x.requires_grad, self.m.parameters()))
        prev_min_loss, early_stop_count = 1 << 30, cfg.early_stop_count
        for epoch in range(self.base_epoch + cfg.rl_epoch_num + 1):
            mode = 'rl'
            if epoch <= self.base_epoch:
                continue
            epoch_loss, cnt = 0,0
            data_iterator = self.reader.mini_batch_iterator('train')
            optim = self.optim #Adam(lr=lr, params=filter(lambda x: x.requires_grad, self.m.parameters()), weight_decay=0)
            for iter_num, dial_batch in enumerate(data_iterator):
                turn_states = {}
                prev_z = None
                prev_z1 = None
                prev_z2 = None
                prev_z3 = None
                for turn_num, turn_batch in enumerate(dial_batch):
                    optim.zero_grad()
                    u_input, u_input_np, z_input,z1_input,z2_input,z3_input, m_input, m_input_np, u_len, \
                    m_len, degree_input, kw_ret \
                        = self._convert_batch(turn_batch, prev_z,prev_z1,prev_z2,prev_z3)
                    loss_rl = self.m(u_input=u_input, z_input=z_input,z1_input=z1_input,z2_input=z2_input,z3_input=z3_input,
                                m_input=m_input,
                                degree_input=degree_input,
                                u_input_np=u_input_np,
                                m_input_np=m_input_np,
                                turn_states=turn_states,
                                dial_id=turn_batch['dial_id'],
                                u_len=u_len, m_len=m_len, mode=mode, **kw_ret)

                    if loss_rl is not None:
                        loss = loss_rl #+ loss_mle * 0.1
                        loss.backward()
                        grad = torch.nn.utils.clip_grad_norm(self.m.parameters(), 2.0)
                        optim.step()
                        epoch_loss += loss.data.cpu().numpy()[0]
                        cnt += 1
                        logging.debug('{} loss {}, grad:{}'.format(mode,loss.data[0],grad))

                    prev_z = turn_batch['bspan']

            epoch_sup_loss = epoch_loss / (cnt + 1e-8)
            logging.info('avg training loss in epoch %d sup:%f' % (epoch, epoch_sup_loss))

            valid_sup_loss, valid_unsup_loss = self.validate()
            logging.info('validation loss in epoch %d sup:%f unsup:%f' % (epoch, valid_sup_loss, valid_unsup_loss))
            valid_loss = valid_sup_loss + valid_unsup_loss

            #self.save_model(epoch)

            if valid_loss <= prev_min_loss:
                self.save_model(epoch)
                prev_min_loss = valid_loss
            else:
                early_stop_count -= 1
                lr *= cfg.lr_decay
                if not early_stop_count:
                    break
                logging.info('early stop countdown %d, learning rate %f' % (early_stop_count, lr))

    def save_model(self, epoch, path=None, critical=False):
        if not path:
            path = cfg.model_path
        if critical:
            path += '.final'
        all_state = {'lstd': self.m.state_dict(),
                     'config': cfg.__dict__,
                     'epoch': epoch}
        torch.save(all_state, path)

    def load_model(self, path=None):
        if not path:
            path = cfg.model_path
        all_state = torch.load(path, map_location='cpu')
        self.m.load_state_dict(all_state['lstd'])
        self.base_epoch = all_state.get('epoch', 0)

    def training_adjust(self, epoch):
        return

    def freeze_module(self, module):
        for param in module.parameters():
            param.requires_grad = False

    def unfreeze_module(self, module):
        for param in module.parameters():
            param.requires_grad = True

    def load_glove_embedding(self, freeze=False):
        initial_arr = self.m.u_encoder.embedding.weight.data.cpu().numpy()
        embedding_arr = torch.from_numpy(get_glove_matrix(self.reader.vocab, initial_arr))

        self.m.u_encoder.embedding.weight.data.copy_(embedding_arr)
        #self.m.z_decoder.emb.weight.data.copy_(embedding_arr)
        self.m.z1_decoder.emb.weight.data.copy_(embedding_arr)
        # self.m.z2_decoder.emb.weight.data.copy_(embedding_arr)
        self.m.z3_decoder.emb.weight.data.copy_(embedding_arr)
        self.m.m_decoder.emb.weight.data.copy_(embedding_arr)

    def count_params(self):

        module_parameters = filter(lambda p: p.requires_grad, self.m.parameters())
        param_cnt = sum([np.prod(p.size()) for p in module_parameters])

        print('total trainable params: %d' % param_cnt)


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('-mode')
    parser.add_argument('-model')
    parser.add_argument('-cfg', nargs='*')
    args = parser.parse_args()

    cfg.init_handler(args.model)
    cfg.dataset = args.model.split('-')[-1]

    if args.cfg:
        for pair in args.cfg:
            k, v = tuple(pair.split('='))
            dtype = type(getattr(cfg, k))
            if dtype == type(None):
                raise ValueError()
            if dtype is bool:
                v = False if v == 'False' else True
            else:
                v = dtype(v)
            setattr(cfg, k, v)

    logging.info(str(cfg))
    if cfg.cuda:
        torch.cuda.set_device(cfg.cuda_device)
        logging.info('Device: {}'.format(torch.cuda.current_device()))
    cfg.mode = args.mode

    torch.manual_seed(cfg.seed)
    torch.cuda.manual_seed(cfg.seed)
    random.seed(cfg.seed)
    np.random.seed(cfg.seed)

    m = Model(args.model.split('-')[-1])
    m.count_params()
    print("Mode: ",args.mode)
    if args.mode == 'train':
        m.load_glove_embedding()
        m.train()
    elif args.mode == 'adjust':
        m.load_model()
        m.train()
    elif args.mode == 'test':
        print("test begin")
        m.load_model()
        m.eval()
        print("test end")
    elif args.mode == 'rl':
        m.load_model()
        m.reinforce_tune()


if __name__ == '__main__':
    main()
