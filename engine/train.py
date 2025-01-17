
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import tensorflow as tf
tf.compat.v1.enable_eager_execution()

import sys
import os

import warnings

from tensorflow import keras
import numpy as np
from tensorflow.data import Dataset
from engine.image import *
import tensorflow.image

import numpy as np
import json
import cv2
import time
import json


def load_data(paths, train = True):
    '''
    objective: load image files
    param: paths to each image files
    return: image files of input image and ground-truth image
    '''
    for img_path in paths:
        gt_path = img_path.decode("utf-8").replace('.jpg','.h5').replace('images','ground-truth')
        img = tf.io.read_file(img_path)
        img = tf.image.decode_jpeg(img, channels = 3)
        img = tf.cast(img, tf.float32)
        img = img/255.0  # normalizing the images to [0,1]

        gt_file = h5py.File(gt_path, 'r')
        target = np.asarray(gt_file['density'])

        target = cv2.resize(target,(int(target.shape[1]/8),int(target.shape[0]/8)),interpolation = cv2.INTER_CUBIC)*64


        yield (img, target)

def load_best_vals():
	'''
	objective: load best mae values from previous values
	'''
	val = json.load(open('best_vals.txt', 'r'))
	return val['best_mae_a'], val['best_mae_b']

def reset_best_vals(best_mae_a, best_mae_b):
	'''
	objective: store best mae values 
	'''
	mae_dict = {
		'best_mae_a': best_mae_a,
		'best_mae_b': best_mae_b
	}
	# store a text file
	with open('best_vals.txt', 'w') as json_file:
		json.dump(mae_dict, json_file)

def load_datasets():
	'''
	objective: load datasets from lists of paths and apply load function
	return: train_dataset, test_dataset - tf.data.Dataset
	'''
	train_a_list, test_a_list, train_b_list, test_b_list = load_data_list()

	# part_A
	# load dataset from generator defined as load_data
	train_a_dataset = tf.data.Dataset.from_generator(
		load_data, args = [train_a_list],output_types = (tf.float32, tf.float32), output_shapes = ((None,None,3), (None,None)))
	train_a_dataset = train_a_dataset.shuffle(100000)

	test_a_dataset = tf.data.Dataset.from_generator(
		load_data, args = [test_a_list], output_types = (tf.float32, tf.float32), output_shapes = ((None,None,3), (None,None)))
	
	# part_B
	train_b_dataset = tf.data.Dataset.from_generator(
		load_data, args = [train_b_list],output_types = (tf.float32, tf.float32), output_shapes = ((None,None,3), (None,None)))
	train_b_dataset = train_b_dataset.shuffle(100000)

	test_b_dataset = tf.data.Dataset.from_generator(
		load_data, args = [test_b_list], output_types = (tf.float32, tf.float32), output_shapes = ((None,None,3), (None,None)))
	

	return train_a_dataset, test_a_dataset, train_b_dataset, test_b_dataset

def loss_fn(model, input_image, gt_image):
	'''
	objective: calculate loss from input image and ground-truth
	return: loss 
	'''
	output = model(np.expand_dims(input_image,0), training = True)
	output = tf.squeeze(output, [0,3])
    # mean squared error
	loss = tf.reduce_mean(tf.square(output - gt_image))
	return loss

def grad(model, input_image, gt_image):
	'''
	objective: apply gradient descent method to update model's weights
	'''
	with tf.GradientTape() as tape:
		loss = loss_fn(model, input_image, gt_image)
	return tape.gradient(loss, model.trainable_weights)

def fit(model, part, epochs, learning_rate = 0.0001):
	'''
	train model with part variable ("A" or "B") 
	'''
	if part == "A":
		train_dataset, test_dataset, b_train, b_test = load_datasets()
		# get lowest mae from previous trained models to compare
		# if it's lower than those values, store the whole model into h5 file
		best_mae, _ = load_best_vals()
		progress_range = 44850

	elif part == "B":
		a_train, a_test, train_dataset, test_dataset = load_datasets()
		_, best_mae = load_best_vals()
		progress_range = 79800

	else: return("Please put A or B")

	optimizer = tf.keras.optimizers.Adam(learning_rate = learning_rate)
	
	# train model
	print('Part {} Learning started. It takes sometime.'.format(part))

	for epoch in range(epochs):
		# init values
		avg_loss = 0.
		train_step = 0
		test_step = 0
		test_mae = 0

		loss_list = []
		progress = ProgressMonitor(length = progress_range)

		# train process
		for step, (images, gt_images) in enumerate(train_dataset):

			grads = grad(model, images, gt_images)
			optimizer.apply_gradients(zip(grads, model.trainable_variables))
			loss = loss_fn(model, images, gt_images)
			avg_loss += loss
			train_step += 1

			loss_list.append(loss)
			progress.update(step, sum(loss_list)/len(loss_list))

		avg_loss = avg_loss / train_step

		# test process
		for step, (images, gt_images) in enumerate(test_dataset): 

			output = model(np.expand_dims(images,0))
			test_step += 1

			test_mae += abs(np.sum(output)-np.sum(gt_images))

		test_mae = test_mae / test_step


		print('Epoch:', '{}'.format(epoch + 1), 
		      'Test MAE = ', '{:.5f}'.format(test_mae))

	# when test_mae is smaller than the stored lowest mae,
	# store whole model into h5 file
	if (test_mae < best_mae): 
		model.save('part_{}_best_model_{}.h5'.format(part, epochs))
		if part == "A":
			reset_best_vals(test_mae, _)
		else:
			reset_best_vals(_, test_mae)

	print('Learning Finished!')

	return model
	
