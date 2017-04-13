from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf
from tensorflow.contrib import seq2seq
import sonnet as snt


class Encoder(snt.AbstractModule):
    def __init__(self, vocab_size, 
                 embedding_dim=128, 
                 rnn_hidden_dim=128, 
                 rnn_type="lstm", 
                 num_rnn_layers=1, 
                 is_bidi=True, 
                 reverse_sequence=True,
                 is_skip_connections=False, 
                 add_attention=True,
                 name="encoder"):
        super(Encoder, self).__init__(name=name)

        self._vocab_size = vocab_size
        self._embedding_dim = embedding_dim
        self._rnn_hidden_dim = rnn_hidden_dim

        self._rnn_type = rnn_type
        self._num_rnn_layers = num_rnn_layers
        self._is_bidi = is_bidi
        self._is_skip_connections = is_skip_connections
        self._add_attention = add_attention
        self._reverse_sequence = reverse_sequence

        with self._enter_variable_scope():
            self._embedding_layer = snt.Embed(
                vocab_size, embedding_dim, existing_vocab=None)

            rnn_cell = lambda i: snt.LSTM(rnn_hidden_dim, name="lstm_{}".format(i))
            rnn_layers = [rnn_cell(i) for i in range(num_rnn_layers)]
            self._cell = snt.DeepRNN(rnn_layers, skip_connections=is_skip_connections)

    def _build(self, encoder_inputs, sequence_length):
        batch_size = tf.shape(encoder_inputs)[0]
        initial_state = self._cell.initial_state(batch_size)

        if self._reverse_sequence:
            encoder_inputs = tf.reverse_sequence(encoder_inputs, sequence_length,seq_axis=1)

        batch_embedding_layer = snt.BatchApply(self._embedding_layer)
        embedding_outputs = batch_embedding_layer(encoder_inputs)

        if self._is_bidi:
            rnn_outputs, final_state = tf.nn.bidirectional_dynamic_rnn(          
                    cell_fw=self._cell, cell_bw=self._cell,
                    inputs=embedding_outputs,
                    time_major=False,
                    initial_state_fw=initial_state,
                    initial_state_bw=initial_state,
                    sequence_length=sequence_length)
            rnn_outputs = tf.concat(rnn_outputs, axis=2)
        else:
            rnn_outputs, final_state = tf.nn.dynamic_rnn(          
                cell=self._cell,
                inputs=embedding_outputs,
                time_major=False,
                initial_state=initial_state,
                sequence_length=sequence_length)

        final_state = final_state[-1]  # last RNN layer output
        if isinstance(final_state, tuple):
            final_state = final_state[0]  # assuming h is first dimension

        if self._add_attention:
            encoder_outputs = rnn_outputs
        else:
            encoder_outputs = final_state
        return encoder_outputs


class Decoder(snt.AbstractModule):
    def __init__(self, vocab_size, 
                 embedding_dim=128, 
                 rnn_hidden_dim=128, 
                 attention_hidden_dims=128, 
                 rnn_type="lstm", 
                 add_attention=True, 
                 attention_type="luong", 
                 name="decoder"):
        super(Decoder, self).__init__(name=name)

        self._vocab_size = vocab_size
        self._embedding_dim = embedding_dim
        self._rnn_hidden_dim = rnn_hidden_dim

        self._add_attention = add_attention
        self._attention_hidden_dims = attention_hidden_dims
        self._attention_type = attention_type

        with self._enter_variable_scope():
            self._embedding_layer = snt.Embed(
                vocab_size, embedding_dim, existing_vocab=None)

            if self._add_attention:
                if attention_type == "luong":
                    self._create_attention_mechanism = seq2seq.LuongAttention
                elif attention_type == "bahdanaeu":
                    self._create_attention_mechanism = seq2seq.BahdanauAttention

            self._cell = snt.LSTM(rnn_hidden_dim, name="decoder_lstm")

    def _build(self, encoder_outputs, encoder_sequence_length, decoder_inputs, decoder_sequence_length):
        # TODO: use final_outputs if not using attention
        batch_size = tf.shape(encoder_outputs)[0]

        batch_embedding_layer = snt.BatchApply(self._embedding_layer)
        embedding_outputs = batch_embedding_layer(decoder_inputs)

        # TODO: use GreedyEmbeddingsHelper for inference
        helper = seq2seq.TrainingHelper(embedding_outputs, decoder_sequence_length)

        cell = self._cell

        if self._add_attention:
            attention_mechanism = self._create_attention_mechanism(
                num_units=self._attention_hidden_dims,
                memory=encoder_outputs,
                memory_sequence_length=encoder_sequence_length)

            cell = seq2seq.DynamicAttentionWrapper(
                cell,
                attention_mechanism,
                attention_size=self._attention_hidden_dims,
                output_attention=True if self._attention_type == "luong" else False)

        decoder = seq2seq.BasicDecoder(
            cell=cell,
            helper=helper,
            initial_state=cell.zero_state(
                dtype=tf.float32, batch_size=batch_size))

        final_outputs, final_state = seq2seq.dynamic_decode(decoder)

        decoder_outputs = final_outputs.rnn_output
        return decoder_outputs


class Seq2Seq(snt.AbstractModule):
    def __init__(self, encoder, decoder,
                 name="seq2seq"):
        super(Seq2Seq, self).__init__(name=name)

        self._encoder = encoder
        self._decoder = decoder

        assert encoder._add_attention == decoder._add_attention, "Attention option needs to sync."

    def _build(self, source_word_ids, target_word_ids):
        self.preprocess(source_word_ids)
        self.preprocess(target_word_ids)

    @staticmethod
    def preprocess(vector):
        pass



def _test():
    source = tf.constant([[0,1,2,3], [0,1,2,3]])
    source_sequence_length = [4, 4]
    target = tf.constant([[0,1,2,3], [0,1,2,3]])
    target_sequence_length = [4, 4]

    encoder = Encoder(4, num_rnn_layers=2)
    decoder = Decoder(4, add_attention=True)

    encoder_outputs = encoder(source, sequence_length=source_sequence_length)
    decoder_outputs = decoder(encoder_outputs, source_sequence_length, target, target_sequence_length)

    with tf.Session() as sess:
        sess.run(tf.global_variables_initializer())
        sess.run(tf.local_variables_initializer())
        print(sess.run(decoder_outputs))


if __name__ == "__main__":
    _test()