"""
first input??
try grouping
"""

# Load lang model

import os
import time
import pickle

import argparse
import numpy as np
import tensorflow as tf
# from lm_utils import build_dataset_no_eos, batch_iter
from dsr.language_model.lm_utils import build_dataset_with_eos_padding, batch_iter

from dsr.language_model.model.model_dyn_rnn import DynRNNLanguageModel

class LModel(object):
    def __init__(self, dsr_function_set, dsr_n_input_var, 
                saved_lmodel_path, saved_lmodel_lib,
                embedding_size=32, num_layers=1, num_hidden=256,
                prob_sharing=True
                ):
        self.dsr_n_input_var = dsr_n_input_var
        self.prob_sharing = prob_sharing

        with open(saved_lmodel_lib,'rb') as f:
            self.lm_token2idx = pickle.load(f)
        self.dsr2lm, self.lm2dsr = self.set_lib_to_lib(dsr_function_set,dsr_n_input_var)

        self.lmodel = DynRNNLanguageModel(len(self.lm_token2idx), embedding_size, num_layers, num_hidden, mode='predict')
        self.lsess = self.load_model(saved_lmodel_path)
        self.next_state = None

        # def _state_after_initial():

    def load_model(self, saved_lmodel_path):
        sess = tf.compat.v1.Session()
        saver = tf.train.Saver()
        saver.restore(sess,tf.train.latest_checkpoint(saved_lmodel_path))
        return sess

    def set_lib_to_lib(self, dsr_function_set, dsr_n_input_var):
        """
        dsr2lm: len(dsr)
        lm2dsr: len(lm)
        
        need to handle terminals! constant!
        """
        dsr2lm = [self.lm_token2idx['TERMINAL'] for _ in range(dsr_n_input_var)]
        dsr2lm += [self.lm_token2idx[func.lower()] for func in dsr_function_set] # ex) [1,1,1,2,3,4,5,6,7,8,9]
        
        lm2dsr = {lm_idx: i for i, lm_idx in enumerate(dsr2lm)}

        # todo: if missing in lm

        return dsr2lm, lm2dsr

    def get_lm_prior(self, next_input):
        def _prep(next_input):
            """
            match library and return as lang model's input

            next_input: array, shape = (batch size)
            next_token: np.ndarry, shape = (batch size,)
            """
            next_token = np.array(self.dsr2lm)[next_input]

            return np.array([next_token]) 

        def _logit_to_prior(logit):
            """
            return as make_prior
            logit: np.ndarray, shape = (1,batch size, lm size)
            prior: np.ndarray, shape = (batch size, dsr size)
            """

            # sharing probability among same tokens (e.g., TERMINAL to multiple variables)
            if self.prob_sharing is True:
                # A
                # continue
                # B
                logit[:,:,self.lm_token2idx['TERMINAL']] = logit[:,:,self.lm_token2idx['TERMINAL']] - np.log(self.dsr_n_input_var)
                # C
                # logit[:,:,self.lm_token2idx['TERMINAL']] = logit[:,:,self.lm_token2idx['TERMINAL']] - np.log((self.dsr_n_input_var-1)*np.exp(logit[:,:,self.lm_token2idx['TERMINAL']])+self.dsr_n_input_var)

            prior = logit[0,:,self.dsr2lm]
            prior = np.transpose(prior)

            return prior

        feed_dict = {self.lmodel.x: _prep(next_input), self.lmodel.keep_prob: 1.0}
        if self.next_state is not None: # not the first input
            feed_dict.update({self.lmodel.initial_state: self.next_state})

        self.next_state, lm_logit = self.lsess.run([self.lmodel.last_state, self.lmodel.logits], feed_dict=feed_dict)

        lm_prior = _logit_to_prior(lm_logit)
        
        return lm_prior




##########
### model test
def predict(saved_path, predict_data, vocabulary_size, embedding_size=32, num_layers=1, num_hidden=256, batch_size=1):
    with tf.compat.v1.Session() as sess:
        
        # if args.model == "rnn":
        #     model = RNNLanguageModel(vocabulary_size, args)
        # elif args.model == "birnn":
        #     model = BiRNNLanguageModel(vocabulary_size, args)
        # elif args.model == "dynrnn":
        #     model = DynRNNLanguageModel(vocabulary_size, args)
        # else:
        #     raise ValueError("Not Implemented {}.".format(args.model))

        model = DynRNNLanguageModel(vocabulary_size, embedding_size, num_layers, num_hidden, mode='predict')


        # Load model
        saver = tf.train.Saver()
        saver.restore(sess,tf.train.latest_checkpoint(saved_path))

        test_batches = batch_iter(predict_data, batch_size, 1)

        for test_x in test_batches:
            # first
            feed_dict = {model.x: test_x[:,:1], model.keep_prob: 1.0}
            next_state, logits, lm_input, init_state = sess.run([model.last_state, model.logits, model.lm_input, model.initial_state], feed_dict=feed_dict)

            # second to last
            for i in range(1,2):
                feed_dict = {model.x: test_x[:,i:i+1], model.keep_prob: 1.0, model.initial_state: next_state}
                next_state, logits, lm_input, init_state = sess.run([model.last_state, model.logits, model.lm_input, model.initial_state], feed_dict=feed_dict)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="dynrnn", help="rnn | birnn")
    parser.add_argument("--embedding_size", type=int, default=32, help="embedding size.")
    parser.add_argument("--num_layers", type=int, default=1, help="RNN network depth.")
    parser.add_argument("--num_hidden", type=int, default=256, help="RNN network size.")
    parser.add_argument("--keep_prob", type=float, default=0.5, help="dropout keep prob.")
    parser.add_argument("--learning_rate", type=float, default=1e-3, help="learning rate.")

    parser.add_argument("--batch_size", type=int, default=1, help="batch size.")
    parser.add_argument("--num_epochs", type=int, default=30, help="number of epochs.")

    parser.add_argument("--saved_path", type=str, default="/Users/kim102/OneDrive - LLNL/git/equation_language_model/results/dynrnn-(ep_10,la_1,kp_0.5,bs_64)-2001251717/saved_model", help="trained model")
    args = parser.parse_args()


    # log_print(args)

    predict_data = np.array([[2,1], [2]])
    # train_file = "ptb_data/ptb.train.txt"
    # train_data, test_data = build_dataset(train_file, word_dict)

    # predict_, _, word_dict = build_dataset_no_eos(predict_input=predict_data, test_size=0.01)
    predict_, _, word_dict = build_dataset_with_eos_padding(predict_input=predict_data, test_size=0.01)
    
    # log_print(predict_.shape)


    predict(os.path.join(args.saved_path,'saved_model'), predict_, len(word_dict), args.embedding_size, args.num_layers, args.num_hidden, args.batch_size)
    
