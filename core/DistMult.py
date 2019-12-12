#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import tensorflow as tf

from pykg2vec.core.KGMeta import ModelMeta


class DistMult(ModelMeta):
    """`EMBEDDING ENTITIES AND RELATIONS FOR LEARNING AND INFERENCE IN KNOWLEDGE BASES`_

        DistMult is a simpler model comparing with RESCAL in that it simplifies
        the weight matrix used in RESCAL to a diagonal matrix. The scoring
        function used DistMult can capture the pairwise interactions between
        the head and the tail entities. However, DistMult has limitation on modeling
        asymmetric relations.

        Args:
            config (object): Model configuration parameters.

        Attributes:
            config (object): Model configuration.
            data_stats (object): ModelMeta object instance. It consists of the knowledge graph metadata.
            tot_ent (int): Total unique entites in the knowledge graph.
            tot_rel (int): Total unique relation in the knowledge graph.
            model (str): Name of the model.

        Examples:
            >>> from pykg2vec.core.Complex import DistMult
            >>> from pykg2vec.utils.trainer import Trainer
            >>> model = DistMult()
            >>> trainer = Trainer(model=model, debug=False)
            >>> trainer.build_model()
            >>> trainer.train_model()

        .. _EMBEDDING ENTITIES AND RELATIONS FOR LEARNING AND INFERENCE IN KNOWLEDGE BASES:
            https://arxiv.org/pdf/1412.6575.pdf

    """

    def __init__(self, config=None):
        self.config = config
        self.data_stats = self.config.kg_meta
        self.tot_ent = self.data_stats.tot_entity
        self.tot_rel = self.data_stats.tot_relation
        self.model_name = 'DistMult'

    def def_inputs(self):
        """Defines the inputs to the model.
           
           Attributes:
               h (Tensor): Head entities ids.
               r (Tensor): Relation ids of the triple.
               t (Tensor): Tail entity ids of the triple.
               hr_t (Tensor): Tail tensor list for (h,r) pair.
               rt_h (Tensor): Head tensor list for (r,t) pair.
               test_h_batch (Tensor): Batch of head ids for testing.
               test_r_batch (Tensor): Batch of relation ids for testing
               test_t_batch (Tensor): Batch of tail ids for testing.
        """
        self.h = tf.compat.v1.placeholder(tf.int32, [None])
        self.r = tf.compat.v1.placeholder(tf.int32, [None])
        self.t = tf.compat.v1.placeholder(tf.int32, [None])
        self.hr_t = tf.compat.v1.placeholder(tf.float32, [None, self.data_stats.tot_entity])
        self.rt_h = tf.compat.v1.placeholder(tf.float32, [None, self.data_stats.tot_entity])

        self.test_h_batch = tf.compat.v1.placeholder(tf.int32, [None])
        self.test_r_batch = tf.compat.v1.placeholder(tf.int32, [None])
        self.test_t_batch = tf.compat.v1.placeholder(tf.int32, [None])

    def def_parameters(self):
        """Defines the model parameters.
           
           Attributes:
               k (Tensor): Size of the latent dimesnion for entities and relations.
               ent_embeddings(Tensor Variable): Lookup variable containing embedding of entities.
               rel_embeddings (Tensor Variable): Lookup variable containing embedding of relations.
               parameter_list  (list): List of Tensor parameters. 
        """
        k = self.config.hidden_size
        with tf.compat.v1.name_scope("embedding"):
            self.ent_embeddings = tf.compat.v1.get_variable(name="emb_e_real", shape=[self.tot_ent, k],
                                            initializer=tf.compat.v1.keras.initializers.VarianceScaling(scale=1.0, mode="fan_avg", distribution=("uniform" if False else "truncated_normal")))
            self.rel_embeddings = tf.compat.v1.get_variable(name="emb_rel_real", shape=[self.tot_rel, k],
                                            initializer=tf.compat.v1.keras.initializers.VarianceScaling(scale=1.0, mode="fan_avg", distribution=("uniform" if False else "truncated_normal")))

        self.parameter_list = [self.ent_embeddings, self.rel_embeddings]

    def def_loss(self):
        """Defines the loss function for the algorithm."""
        h_emb, r_emb, t_emb = self.embed(self.h, self.r, self.t)

        pred_tails = tf.matmul(h_emb * r_emb, tf.transpose(a=tf.nn.l2_normalize(self.ent_embeddings, axis=1)))
        pred_heads = tf.matmul(t_emb * r_emb, tf.transpose(a=tf.nn.l2_normalize(self.ent_embeddings, axis=1)))

        pred_tails = tf.nn.relu(pred_tails)
        pred_heads = tf.nn.relu(pred_heads)

        hr_t = self.hr_t #* (1.0 - self.config.label_smoothing) + 1.0 / self.data_stats.tot_entity
        rt_h = self.rt_h #* (1.0 - self.config.label_smoothing) + 1.0 / self.data_stats.tot_entity

        loss_tails = tf.reduce_mean(input_tensor=tf.keras.backend.binary_crossentropy(hr_t, pred_tails))
        loss_heads = tf.reduce_mean(input_tensor=tf.keras.backend.binary_crossentropy(rt_h, pred_heads))

        self.loss = loss_tails + loss_heads

    def test_batch(self):
        """Function that performs batch testing for the algorithm.

            Returns:
                Tensors: Returns ranks of head and tail.
        """
        h_emb, r_emb, t_emb = self.embed(self.test_h_batch, self.test_r_batch, self.test_t_batch)

        pred_tails = tf.matmul(h_emb * r_emb, tf.transpose(a=tf.nn.l2_normalize(self.ent_embeddings, axis=1)))
        pred_tails = tf.nn.relu(pred_tails)

        pred_heads = tf.matmul(t_emb * r_emb, tf.transpose(a=tf.nn.l2_normalize(self.ent_embeddings, axis=1)))
        pred_heads = tf.nn.relu(pred_heads)

        _, head_rank = tf.nn.top_k(-pred_heads, k=self.data_stats.tot_entity)
        _, tail_rank = tf.nn.top_k(-pred_tails, k=self.data_stats.tot_entity)

        return head_rank, tail_rank

    def embed(self, h, r, t):
        """Function to get the embedding value.
           
           Args:
               h (Tensor): Head entities ids.
               r (Tensor): Relation ids of the triple.
               t (Tensor): Tail entity ids of the triple.

            Returns:
                Tensors: Returns head, relation and tail embedding Tensors.
        """
        norm_ent_embeddings = tf.nn.l2_normalize(self.ent_embeddings, axis=1)
        norm_rel_embeddings = tf.nn.l2_normalize(self.rel_embeddings, axis=1)

        h_emb = tf.nn.embedding_lookup(params=norm_ent_embeddings, ids=h)
        r_emb = tf.nn.embedding_lookup(params=norm_rel_embeddings, ids=r)
        t_emb = tf.nn.embedding_lookup(params=norm_ent_embeddings, ids=t)

        return h_emb, r_emb, t_emb

    def get_embed(self, h, r, t, sess=None):
        """Function to get the embedding value in numpy.
           
           Args:
               h (Tensor): Head entities ids.
               r (Tensor): Relation ids of the triple.
               t (Tensor): Tail entity ids of the triple.
               sess (object): Tensorflow Session object.

            Returns:
                Tensors: Returns head, relation and tail embedding Tensors.
        """
        h, r, t = self.embed(h, r, t)
        return sess.run([h, r, t])

    def get_proj_embed(self, h, r, t, sess):
        """Function to get the projected embedding value in numpy.
           
           Args:
               h (Tensor): Head entities ids.
               r (Tensor): Relation ids of the triple.
               t (Tensor): Tail entity ids of the triple.
               sess (object): Tensorflow Session object.

            Returns:
                Tensors: Returns head, relation and tail embedding Tensors.
        """
        return self.get_embed(h, r, t, sess)

