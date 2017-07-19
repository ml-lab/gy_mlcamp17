from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os.path
import tensorflow as tf
import numpy as np
import datetime

from sketch_data_handler import *
from pen_data_handler import *
from test_data_handler import *
import cycle_gan

time_now = datetime.datetime.now()

def get_summary_path():
  path = "checkpoints/output_%02d_%02d_%02d_%02d" % (time_now.month, time_now.day,
      time_now.hour, time_now.minute)
  return path

def get_output_model_path():

  path = "checkpoints/output_%02d_%02d_%02d_%02d" % (time_now.month, time_now.day,
      time_now.hour, time_now.minute)
  return path

def parse_arguments():
  tf.flags.DEFINE_integer('batch_size', 16, 'batch size, default: 16')
  tf.flags.DEFINE_integer('target_size', 256, 'Image size, default: 256')
  tf.flags.DEFINE_integer(
      'num_block', 4, 'the number of residual block, default: 4')
  tf.flags.DEFINE_integer(
      'log_step', 100, 'How often write the summary, default: 100')
  tf.flags.DEFINE_string('X', 'sketch_list.txt',
      'text file that contains paths of files for Dataset X. default: sketch_list.txt')
  tf.flags.DEFINE_string('Y', 'pen_list.txt',
      'text file that contains paths of files for Dataset Y. default: pen_list.txt')
  tf.flags.DEFINE_string('output_model_path', get_output_model_path(),
      'output model path to save trained model. default: None(automatic)')
  tf.flags.DEFINE_string('summary_path', get_summary_path(),
      'summary path. default: None(automatic)')
  tf.flags.DEFINE_string('saved_model_path', None,
      'model path to restore and continue training. default: None')
  tf.flags.DEFINE_string('mode', 'train', 
      'execution mode(train or test), default: train')

def test():
  FLAGS = tf.flags.FLAGS
  is_training = False

  graph = tf.Graph()
  max_size = 1024

  with graph.as_default():
    data_handler_X = TestDataHandler(FLAGS.X, max_size=max_size)
    num_test = data_handler_X.num_test()

    input_X = tf.placeholder_with_default(
        tf.zeros([1, max_size, max_size, 1]),
        [1, max_size, max_size, 1], name='input_X')

    input_Y = tf.placeholder_with_default(
        tf.zeros([1, max_size, max_size, 1]),
        [1, max_size, max_size, 1], name='input_Y')

    # --------------------------------------------------------------------
    # Model here
    # --------------------------------------------------------------------

    [ train_op, losses, predictions ] = cycle_gan.build_model(
        input_X, input_Y, is_training=False)


    model_saver = tf.train.Saver()

  with tf.Session(graph=graph) as sess:
    if FLAGS.saved_model_path is not None:
      model_saver.restore(sess, tf.train.latest_checkpoint(FLAGS.saved_model_path))
      step = 0
    else:
      print("model path is required for test run")
      exit(-1)


    for step in range(num_test):
      fetch_dict = {
          "X_after_AE": predictions["Y_from_X"],
      }

      img, original_size, resized_size = data_handler_X.next()
      ori_img = img * 128.0 + 128.0
      ori_img = ori_img.reshape([max_size, max_size])
      scipy.misc.imsave('original_%06d.png' % step, ori_img) 

      result = sess.run(fetch_dict,
          feed_dict={input_X: img})

      # Crop and 
      pen_img = result["X_after_AE"]
      height, width = resized_size
      pen_img = pen_img.reshape([max_size, max_size])
      pen_img = pen_img[0:height, 0:width]
      pen_img = scipy.misc.imresize(pen_img, original_size)
      pen_img = pen_img * 128.0 + 128.0

      scipy.misc.imsave('%06d.png' % step, pen_img) 

      print("count %d" % (step))

def train():

  FLAGS = tf.flags.FLAGS
  is_training = True
  graph = tf.Graph()

  with graph.as_default():

    data_handler_X = SketchDataHandler(
        FLAGS.X, FLAGS.batch_size, FLAGS.target_size)
    data_handler_Y = PenDataHandler(
        FLAGS.Y, FLAGS.batch_size, FLAGS.target_size)

    #data_handler_Y = PenDataHandler( # FLAGS.X
    #    FLAGS.batch_size, FLAGS.target_size)

    input_X = tf.placeholder_with_default(
        tf.zeros(data_handler_X.get_batch_shape()),
        data_handler_X.get_batch_shape(), name='input_X')
    input_Y = tf.placeholder_with_default(
        tf.zeros(data_handler_Y.get_batch_shape()),
        data_handler_Y.get_batch_shape(), name='input_Y')


    # --------------------------------------------------------------------
    # Model here
    # --------------------------------------------------------------------
    [ train_op, losses, predictions ] = cycle_gan.build_model(input_X, input_Y)

    summary_op = tf.summary.merge([
      tf.summary.image("X/input_X", input_X),
      tf.summary.image("X/Y_from_X", predictions['Y_from_X']),
      tf.summary.image("X/X_cycled", predictions['X_cycled']),
      tf.summary.image("Y/input_Y", input_Y),
      tf.summary.image("Y/X_from_Y", predictions['X_from_Y']),
      tf.summary.image("Y/Y_cycled", predictions['Y_cycled']),
      tf.summary.scalar("loss/loss_DY", losses['loss_DY']),
      tf.summary.scalar("loss/loss_GAN_G", losses['loss_GAN_G']),
      tf.summary.scalar("loss/loss_G", losses['loss_G']),
      tf.summary.scalar("loss/loss_cycle", losses['cycle_loss']),
      ])

    summary_writer = tf.summary.FileWriter(FLAGS.summary_path)
    model_saver = tf.train.Saver(max_to_keep=1000)

  with tf.Session(graph=graph) as sess:
    if FLAGS.saved_model_path is not None:
      model_saver.restore(sess, tf.train.latest_checkpoint(FLAGS.saved_model_path))
      step = int(meta_graph_path.split("-")[2].split(".")[0])
    else:
      sess.run(tf.global_variables_initializer())
      step = 0

    try:
      while True:
        fetch_dict = {
            "train_op": train_op,
            "loss_DY": losses['loss_DY'],
            "loss_G": losses['loss_G'],
        }
        if step % FLAGS.log_step == 0:
          fetch_dict.update({
            "summary": summary_op,
          })

        result = sess.run(fetch_dict,
            feed_dict={input_X: data_handler_X.next(),
              input_Y: data_handler_Y.next(),})

        if step % FLAGS.log_step == 0:
          summary_writer.add_summary(result["summary"], step)
          summary_writer.flush()

        if step % (FLAGS.log_step*10) == 0:
          save_path = model_saver.save(sess, 
              os.path.join(FLAGS.output_model_path, "model.ckpt"),
              global_step= step)

        print("Iter %d, loss_DY %f, loss_G %f" % (step, result["loss_DY"],
          result['loss_G']))
        step += 1
    finally:
      save_path = model_saver.save(sess, 
          os.path.join(FLAGS.output_model_path, "model.ckpt"),
          global_step= step)
      data_handler_X.kill()
      data_handler_Y.kill()

def main(args=None):
  FLAGS = tf.flags.FLAGS
  if FLAGS.mode == 'train':
    train()
  else:
    test()

if __name__ == '__main__':
  parse_arguments()
  tf.app.run()