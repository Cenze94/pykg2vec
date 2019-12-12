#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This module is for evaluating the results
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import numpy as np
import pandas as pd
import timeit
from multiprocessing import Process, Queue
import progressbar

from pykg2vec.core.KGMeta import EvaluationMeta


class MetricCalculator:
    '''
        MetricCalculator aims to 
        1) address all the statistic tasks.
        2) provide interfaces for querying results.

        MetricCalculator is expected to be used by "evaluation_process".
    '''
    def __init__(self, config):
        self.config = config 

        self.hits = config.hits
        self.total_epoch = config.epochs
        self.result_path = config.path_result

        self.hr_t = config.knowledge_graph.read_cache_data('hr_t')
        self.tr_h = config.knowledge_graph.read_cache_data('tr_h')

        self.mean_rank_head = {}
        self.mean_rank_tail = {}
        self.filter_mean_rank_head = {}
        self.filter_mean_rank_tail = {}

        self.hit_head = {}
        self.hit_tail = {}
        self.filter_hit_head = {}
        self.filter_hit_tail = {}
        
        self.mrr ={}
        self.fmrr={}

        self.rank_head = []
        self.rank_tail = []
        self.filter_rank_head = []
        self.filter_rank_tail = []

        self.epoch = None


    def append_result(self, result):
        
        id_replace_tail = result[0]
        id_replace_head = result[1]
        h_list = result[2]
        r_list = result[3]
        t_list = result[4]
        self.epoch = result[5]
        
        total_test = len(h_list)
        
        for triple_id in range(total_test):
            h, r, t = h_list[triple_id], r_list[triple_id], t_list[triple_id]

            t_rank, fil_t_rank = self.get_tail_rank(id_replace_tail[triple_id], h, r, t)
            h_rank, fil_h_rank = self.get_head_rank(id_replace_head[triple_id], h, r, t)

            self.rank_head.append(h_rank)
            self.rank_tail.append(t_rank)

            self.filter_rank_head.append(fil_h_rank)
            self.filter_rank_tail.append(fil_t_rank)

    def get_tail_rank(self, tail_candidate, h, r, t):
        """Function to evaluate the tail rank.
           
           Args:
               id_replace_tail (list): List of the predicted tails for the given head, relation pair
               h (int): head id
               r (int): relation id
               t (int): tail id
               hr_t (dict): list of tails for the given hwS and relation pari.

            Returns:
                Tensors: Returns tail rank and filetered tail rank
        """
        trank = 0
        ftrank = 0

        for j in range(len(tail_candidate)):
            val = tail_candidate[-j - 1]
            if val == t:
                break
            else:
                trank += 1
                ftrank += 1
                if val in self.hr_t[(h, r)]:
                    ftrank -= 1
        
        return trank, ftrank

    def get_head_rank(self, head_candidate, h, r, t):
        """Function to evaluate the head rank.
               
           Args:
               head_candidate (list): List of the predicted head for the given tail, relation pair
               h (int): head id
               r (int): relation id
               t (int): tail id

            Returns:
                Tensors: Returns head  rank and filetered head rank
        """
        hrank = 0
        fhrank = 0

        for j in range(len(head_candidate)):
            val = head_candidate[-j - 1]
            if val == h:
                break
            else:
                hrank += 1
                fhrank += 1
                if val in self.tr_h[(t, r)]:
                    fhrank -= 1

        return hrank, fhrank

    def settle(self):
        self.mean_rank_head[self.epoch] = np.mean(self.rank_head, dtype=np.float32) 
        self.mean_rank_tail[self.epoch] = np.mean(self.rank_tail, dtype=np.float32)

        self.mrr[self.epoch] = np.reciprocal((self.mean_rank_head[self.epoch]+self.mean_rank_tail[self.epoch])/2)

        self.filter_mean_rank_head[self.epoch] = np.mean(self.filter_rank_head, dtype=np.float32) 
        self.filter_mean_rank_tail[self.epoch] = np.mean(self.filter_rank_tail, dtype=np.float32) 

        self.fmrr[self.epoch] = np.reciprocal((self.filter_mean_rank_head[self.epoch]+self.filter_mean_rank_tail[self.epoch])/2)

        for hit in self.hits:
            self.hit_head[(self.epoch, hit)] = np.mean(np.asarray(self.rank_head) < hit, dtype=np.float32) 
            self.hit_tail[(self.epoch, hit)] = np.mean(np.asarray(self.rank_tail) < hit, dtype=np.float32) 
            self.filter_hit_head[(self.epoch, hit)] = np.mean(np.asarray(self.filter_rank_head) < hit, dtype=np.float32) 
            self.filter_hit_tail[(self.epoch, hit)] = np.mean(np.asarray(self.filter_rank_tail) < hit, dtype=np.float32) 

    def get_curr_score(self):
        curr_epoch = self.epoch
        return (self.mean_rank_head[curr_epoch]+self.mean_rank_tail[curr_epoch])/2

    def reset(self):
        self.rank_head = []
        self.rank_tail = []
        self.filter_rank_head = []
        self.filter_rank_tail = []
        self.epoch = None

        self.start_time = timeit.default_timer()

    def save_test_summary(self, model_name):
        """Function to save the test of the summary.
               
            Args:
                result_path (str): Path to save the test summary
                mode_name (str): Name of the model for which the test is performed
                hits (list): list of integet hits for hits@k
                mean_rank_head(dict): mean rank of the head with epoch as key and float as value
                mean_rank_tail (dict): mean rank of the tail with epoch as key and float as value
                filter_mean_rank_head(dict): filtered mean rank of the head with epoch as key and float as value
                filter_mean_rank_tail (dict): filtered mean rank of the head with epoch as key and float as value
                hit_head(dict): mean head hit ratio of the head with epoch,hit as key and float as value
                hit_tail(dict): mean tail hit ratio of the head with epoch,hit as key and float as value
                filter_hit_head(dict): filtered mean head hit ratio of the head with epoch,hit as key and float as value
                ilter_hit_tail(dict): mean tail hit ratio of the head with epoch,hit as key and float as value
                config (object): model configuration object

        """
        files = os.listdir(str(self.result_path))
        l = len([f for f in files if model_name in f if 'Testing' in f])
        with open(str(self.result_path / (model_name + '_summary_' + str(l) + '.txt')), 'w') as fh:
            fh.write('----------------SUMMARY----------------\n')
            for key, val in self.config.__dict__.items():
                if 'gpu' in key:
                    continue
                if 'kg_meta' in key or 'knowledge_graph' in key:
                    continue
                if not isinstance(val, str):
                    if isinstance(val, list):
                        v_tmp = '['
                        for i, v in enumerate(val):
                            if i == 0:
                                v_tmp += str(v)
                            else:
                                v_tmp += ',' + str(v)
                        v_tmp += ']'
                        val = v_tmp
                    else:
                        val = str(val)
                fh.write(key + ':' + val + '\n')
            fh.write('-----------------------------------------\n')
            fh.write("\n----------Metadata Info for Dataset:%s----------------" % self.config.knowledge_graph.dataset_name)
            fh.write("Total Training Triples   :%d\n"%self.config.kg_meta.tot_train_triples)
            fh.write("Total Testing Triples    :%d\n"%self.config.kg_meta.tot_test_triples)
            fh.write("Total validation Triples :%d\n"%self.config.kg_meta.tot_valid_triples)
            fh.write("Total Entities           :%d\n"%self.config.kg_meta.tot_entity)
            fh.write("Total Relations          :%d\n"%self.config.kg_meta.tot_relation)
            fh.write("---------------------------------------------")

        columns = ['Epoch', 'mean_rank', 'filter_mean_rank']
        for hit in self.hits:
            columns += ['hits' + str(hit), 'filter_hits' + str(hit)]

        results = []
        for epoch in self.mean_rank_head.keys():
            res_tmp = [epoch, (self.mean_rank_head[epoch] + self.mean_rank_tail[epoch]) / 2,
                       (self.filter_mean_rank_head[epoch] + self.filter_mean_rank_tail[epoch]) / 2]

            for hit in self.hits:
                res_tmp.append((self.hit_head[(epoch, hit)] + self.hit_tail[(epoch, hit)]) / 2)
                res_tmp.append((self.filter_hit_head[(epoch, hit)] + self.filter_hit_tail[(epoch, hit)]) / 2)
            results.append(res_tmp)

        df = pd.DataFrame(results, columns=columns)

        with open(str(self.result_path / (model_name + '_Testing_results_' + str(l) + '.csv')),
                  'a') as fh:
            df.to_csv(fh)

    def display_summary(self):
        """Function to print the test summary.
               
            Args:
                epoch (int): Epoch for the given result
                hits (list): list of integet hits for hits@k
                mean_rank_head(dict): mean rank of the head with epoch as key and float as value
                mean_rank_tail (dict): mean rank of the tail with epoch as key and float as value
                filter_mean_rank_head(dict): filtered mean rank of the head with epoch as key and float as value
                filter_mean_rank_tail (dict): filtered mean rank of the head with epoch as key and float as value
                hit_head(dict): mean head hit ratio of the head with epoch,hit as key and float as value
                hit_tail(dict): mean tail hit ratio of the head with epoch,hit as key and float as value
                filter_hit_head(dict): filtered mean head hit ratio of the head with epoch,hit as key and float as value
                ilter_hit_tail(dict): mean tail hit ratio of the head with epoch,hit as key and float as value
                start_time (objet): starting time of the evaluation

        """
        self.config.knowledge_graph.dump()

        stop_time = timeit.default_timer()
        print("------Test Results: Epoch: %d --- time: %.2f------------" % (self.epoch, stop_time - self.start_time))
        print('--mean rank          : %.4f' % ((self.mean_rank_head[self.epoch] +
                                                self.mean_rank_tail[self.epoch]) / 2))
        print('--Filtered mean rank : %.4f' % ((self.filter_mean_rank_head[self.epoch] +
                                                self.filter_mean_rank_tail[self.epoch]) / 2))

        print('--MRR(%%)             : %.4f' % (self.mrr[self.epoch]*100))
        print('--Filtered MRR(%%)    : %.4f' % (self.fmrr[self.epoch]*100))

        for hit in self.hits:
            print('--hits%d              : %.4f ' % (hit, (self.hit_head[(self.epoch, hit)] +
                                                          self.hit_tail[(self.epoch, hit)]) / 2))
            print('--Filtered hits%d     : %.4f ' % (hit, (self.filter_hit_head[(self.epoch, hit)] +
                                                          self.filter_hit_tail[(self.epoch, hit)]) / 2))
        print("---------------------------------------------------------")

def evaluation_process(result_queue, output_queue, config, model_name, tuning):
    """ The process that coordinates the tasks of evaluation.
           
        Args:
            result_queue (Queue): Multiprocessing queue to acquire inference result
            output_queue (Queue): Multiprocessing queue to store the evaluation result
            config (object):Model configuration object instance
            model_name (str): Name of the model
            tuning (bool): Check if tuning or performing full test.

    """

    calculator = MetricCalculator(config)

    while True:
        result = result_queue.get()
        
        if result == 'Start!': 
            calculator.reset()
            
        elif result == 'Stop!':
            calculator.settle()
            calculator.display_summary()

            if calculator.epoch >= config.epochs - 1:
                calculator.save_test_summary(model_name)

                if tuning:
                    score = calculator.get_curr_score()
                    output_queue.put(score)

                break
        else:
            calculator.append_result(result)

class Evaluation(EvaluationMeta):
    """Class to perform evaluation of the model.

        Args:
            model (object): Model object
            debug (bool): Flag to check if its debugging
            data_type (str): evaluating 'test' or 'valid'
            tuning (bool): Flag to denoting tuning if True

        Examples:
            >>> from pykg2vec.utils.evaluation import Evaluation
            >>> evaluator = Evaluation(model=model, debug=False, tuning=True)
            >>> evaluator.test_batch(Session(), 0)
            >>> acc = evaluator.output_queue.get()
            >>> evaluator.stop()
    """
    def __init__(self, model=None, debug=False, data_type='valid', tuning=False, session=None):
        
        self.session = session 

        if self.session is None: 
            self.session = tf.compat.v1.Session(config=self.config.gpu_config)
            self.session.run(tf.compat.v1.global_variables_initializer())

        self.model = model
        self.debug = debug
        self.tuning = tuning
        self.result_path = self.model.config.path_result

        if data_type == 'test':
            self.eval_data = self.model.config.knowledge_graph.read_cache_data('triplets_test')
        elif data_type == 'valid':
            self.eval_data = self.model.config.knowledge_graph.read_cache_data('triplets_valid')
        else:
            raise NotImplementedError("%s datatype is not available!" % data_type)

        tot_rows_data = len(self.eval_data)

        '''
            n_test: number of triplets to be tested
            1) if n_test == 0, test all the triplets. 
            2) if n_test >= # of testable triplets, then set n_test to # of testable triplets
        '''
        self.n_test = model.config.test_num
        if self.n_test == 0:
            self.n_test = tot_rows_data
        else:
            self.n_test = min(self.n_test, tot_rows_data)

        ''' 
            loop_len: the # of loops to perform batch evaluation. 
            if debug mode is turned on, then set to only 2. 
        ''' 
        if self.n_test < self.model.config.batch_size_testing:
            self.loop_len = 1
        else:
            self.loop_len = (self.n_test // self.model.config.batch_size_testing) if not self.debug else 2
        
        self.n_test = self.model.config.batch_size_testing * self.loop_len

        '''
            create the process that manages the batched evaluating results.
            result_queue: stores the results for each batch. 
            output_queue: stores the result for a trial, used by bayesian_optimizer.
        '''
        self.result_queue = Queue()
        self.output_queue = Queue()
        self.rank_calculator = Process(target=evaluation_process,
                                       args=(self.result_queue, self.output_queue, 
                                             self.model.config, self.model.model_name, self.tuning))
        self.rank_calculator.start()

    def stop(self):
        """Function that stops the evaluation process"""
        self.rank_calculator.join()
        self.rank_calculator.terminate()

    def test_batch(self, epoch=None):
        """Function that performs the batch testing"""
        
        print("Testing [%d/%d] Triples" % (self.n_test, len(self.eval_data)))

        size_per_batch = self.model.config.batch_size_testing
        head_rank, tail_rank = self.model.test_batch()

        widgets = ['Inferring for Evaluation: ', progressbar.AnimatedMarker(), " Done:",
                   progressbar.Percentage(), " ", progressbar.AdaptiveETA()]

        self.result_queue.put("Start!")
        with progressbar.ProgressBar(max_value=self.loop_len, widgets=widgets) as bar:
            for i in range(self.loop_len):
                data = np.asarray([[self.eval_data[x].h, self.eval_data[x].r, self.eval_data[x].t]
                                   for x in range(size_per_batch * i, size_per_batch * (i + 1))])
                h = data[:, 0]
                r = data[:, 1]
                t = data[:, 2]

                feed_dict = {
                    self.model.test_h_batch: h,
                    self.model.test_r_batch: r,
                    self.model.test_t_batch: t}

                head_tmp, tail_tmp = np.squeeze(self.session.run([head_rank, tail_rank], feed_dict))
                
                result_data = [tail_tmp, head_tmp, h, r, t, epoch]
                self.result_queue.put(result_data)

                bar.update(i)

        self.result_queue.put("Stop!")

    def save_training_result(self, losses):
        """Function that saves training result"""
        files = os.listdir(str(self.result_path))
        l = len([f for f in files if self.model.model_name in f if 'Training' in f])
        df = pd.DataFrame(losses, columns=['Epochs', 'Loss'])
        with open(str(self.result_path / (self.model.model_name + '_Training_results_' + str(l) + '.csv')),
                  'w') as fh:
            df.to_csv(fh)