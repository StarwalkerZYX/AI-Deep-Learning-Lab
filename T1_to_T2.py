# %%
from __future__ import absolute_import, division, print_function, unicode_literals


# %%
from IPython import get_ipython


import tensorflow as tf

import os
import time

from matplotlib import pyplot as plt
from IPython import display

# %%
# 指定CPU计算
os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"  
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

# %%
PATH = 'd:\\T1T2'
T1_PATH = os.path.join(PATH, 'T1')
T2_PATH = os.path.join(PATH, 'T2')

# %%
# Cell 4

def load(image_file):
  image = tf.io.read_file(image_file)
  image = tf.image.decode_bmp(image, channels=3)
  image = image[:, :, :]

  float_image = tf.cast(image, tf.float32)

  return float_image  

# %%
def resize(input_image, height, width):
  input_image = tf.image.resize(input_image, [height, width],
                                method=tf.image.ResizeMethod.NEAREST_NEIGHBOR)
  return input_image


# %%
# Cell 6

# normalizing the images to [-1, 1]
def normalize(input_image):
  input_image = (input_image / 127.5) - 1
  return input_image

# %%
# Cell 8

def load_image(image_file):
  input_image = load(image_file)
  input_image = resize(input_image, 256, 256)
  input_image = normalize(input_image)
  return input_image

# %%
sample_T1 = load_image('D:/T1T2/T1/1.bmp')
plt.figure()
plt.imshow(sample_T1)
plt.show()

# %% [markdown]
# ## Build the Generator
#   * The architecture of generator is a modified U-Net.
#   * Each block in the encoder is (Conv -> Batchnorm -> Leaky ReLU)
#   * Each block in the decoder is (Transposed Conv -> Batchnorm -> Dropout(applied to the first 3 blocks) -> ReLU)
#   * There are skip connections between the encoder and decoder (as in U-Net).
# 
# 

# %%
# Cell 10

OUTPUT_CHANNELS = 3

def downsample(filters, size, apply_batchnorm=True):
  initializer = tf.random_normal_initializer(0., 0.02)

  result = tf.keras.Sequential()
  result.add(
      tf.keras.layers.Conv2D(filters, size, strides=2, padding='same',
                             kernel_initializer=initializer, use_bias=False))

  if apply_batchnorm:
    result.add(tf.keras.layers.BatchNormalization())

  result.add(tf.keras.layers.LeakyReLU())

  return result

down_model = downsample(3, 4)
# %%
# Cell 13

def upsample(filters, size, apply_dropout=False):
  initializer = tf.random_normal_initializer(0., 0.02)

  result = tf.keras.Sequential()
  result.add(
    tf.keras.layers.Conv2DTranspose(filters, size, strides=2,
                                    padding='same',
                                    kernel_initializer=initializer,
                                    use_bias=False))

  result.add(tf.keras.layers.BatchNormalization())

  if apply_dropout:
      result.add(tf.keras.layers.Dropout(0.5))

  result.add(tf.keras.layers.ReLU())

  return result

up_model = upsample(3, 4)

# %%
# Cell 15

def Generator():
  inputs = tf.keras.layers.Input(shape=[256,256,3])

  down_stack = [
    downsample(64, 4, apply_batchnorm=False), # (bs, 128, 128, 64)
    downsample(128, 4), # (bs, 64, 64, 128)
    downsample(256, 4), # (bs, 32, 32, 256)
    downsample(512, 4), # (bs, 16, 16, 512)
    downsample(512, 4), # (bs, 8, 8, 512)
    downsample(512, 4), # (bs, 4, 4, 512)
    downsample(512, 4), # (bs, 2, 2, 512)
    downsample(512, 4), # (bs, 1, 1, 512)
  ]

  up_stack = [
    upsample(512, 4, apply_dropout=True), # (bs, 2, 2, 1024)
    upsample(512, 4, apply_dropout=True), # (bs, 4, 4, 1024)
    upsample(512, 4, apply_dropout=True), # (bs, 8, 8, 1024)
    upsample(512, 4), # (bs, 16, 16, 1024)
    upsample(256, 4), # (bs, 32, 32, 512)
    upsample(128, 4), # (bs, 64, 64, 256)
    upsample(64, 4), # (bs, 128, 128, 128)
  ]

  initializer = tf.random_normal_initializer(0., 0.02)
  last = tf.keras.layers.Conv2DTranspose(OUTPUT_CHANNELS, 4,
                                         strides=2,
                                         padding='same',
                                         kernel_initializer=initializer,
                                         activation='tanh') # (bs, 256, 256, 3)

  x = inputs

  # Downsampling through the model
  skips = []
  for down in down_stack:
    x = down(x)
    skips.append(x)

  skips = reversed(skips[:-1])

  # Upsampling and establishing the skip connections
  for up, skip in zip(up_stack, skips):
    x = up(x)
    x = tf.keras.layers.Concatenate()([x, skip])

  x = last(x)

  return tf.keras.Model(inputs=inputs, outputs=x)

generator = Generator()


# %% [markdown]
# * **Generator loss**
#   * It is a sigmoid cross entropy loss of the generated images and an **array of ones**.
#   * The [paper](https://arxiv.org/abs/1611.07004) also includes L1 loss which is MAE (mean absolute error) between the generated image and the target image.
#   * This allows the generated image to become structurally similar to the target image.
#   * The formula to calculate the total generator loss = gan_loss + LAMBDA * l1_loss, where LAMBDA = 100. This value was decided by the authors of the [paper](https://arxiv.org/abs/1611.07004).
# %% [markdown]
# The training procedure for the generator is shown below:

# %%
# Cell 19
LAMBDA = 100
def generator_loss(disc_generated_output, gen_output, target):
  gan_loss = loss_object(tf.ones_like(disc_generated_output), disc_generated_output)

  # mean absolute error
  l1_loss = tf.reduce_mean(tf.abs(target - gen_output))

  total_gen_loss = gan_loss + (LAMBDA * l1_loss)

  return total_gen_loss, gan_loss, l1_loss

# %% [markdown]
# 
# 
# ![Generator Update Image](https://github.com/tensorflow/docs/blob/master/site/en/tutorials/generative/images/gen.png?raw=1)
# 
# %% [markdown]
# ## Build the Discriminator
#   * The Discriminator is a PatchGAN.
#   * Each block in the discriminator is (Conv -> BatchNorm -> Leaky ReLU)
#   * The shape of the output after the last layer is (batch_size, 30, 30, 1)
#   * Each 30x30 patch of the output classifies a 70x70 portion of the input image (such an architecture is called a PatchGAN).
#   * Discriminator receives 2 inputs.
#     * Input image and the target image, which it should classify as real.
#     * Input image and the generated image (output of generator), which it should classify as fake.
#     * We concatenate these 2 inputs together in the code (`tf.concat([inp, tar], axis=-1)`)

# %%
# Cell 20

def Discriminator():
  initializer = tf.random_normal_initializer(0., 0.02)

  inp = tf.keras.layers.Input(shape=[256, 256, 3], name='input_image')
  tar = tf.keras.layers.Input(shape=[256, 256, 3], name='target_image')

  x = tf.keras.layers.concatenate([inp, tar]) # (bs, 256, 256, channels*2)

  down1 = downsample(64, 4, False)(x) # (bs, 128, 128, 64)
  down2 = downsample(128, 4)(down1) # (bs, 64, 64, 128)
  down3 = downsample(256, 4)(down2) # (bs, 32, 32, 256)

  zero_pad1 = tf.keras.layers.ZeroPadding2D()(down3) # (bs, 34, 34, 256)
  conv = tf.keras.layers.Conv2D(512, 4, strides=1,
                                kernel_initializer=initializer,
                                use_bias=False)(zero_pad1) # (bs, 31, 31, 512)

  batchnorm1 = tf.keras.layers.BatchNormalization()(conv)

  leaky_relu = tf.keras.layers.LeakyReLU()(batchnorm1)

  zero_pad2 = tf.keras.layers.ZeroPadding2D()(leaky_relu) # (bs, 33, 33, 512)

  last = tf.keras.layers.Conv2D(1, 4, strides=1,
                                kernel_initializer=initializer)(zero_pad2) # (bs, 30, 30, 1)

  return tf.keras.Model(inputs=[inp, tar], outputs=last)

discriminator = Discriminator()

# %% [markdown]
# **Discriminator loss**
#   * The discriminator loss function takes 2 inputs; **real images, generated images**
#   * real_loss is a sigmoid cross entropy loss of the **real images** and an **array of ones(since these are the real images)**
#   * generated_loss is a sigmoid cross entropy loss of the **generated images** and an **array of zeros(since these are the fake images)**
#   * Then the total_loss is the sum of real_loss and the generated_loss
# 

# %%
# Cell 23

loss_object = tf.keras.losses.BinaryCrossentropy(from_logits=True)

def discriminator_loss(disc_real_output, disc_generated_output):
  real_loss = loss_object(tf.ones_like(disc_real_output), disc_real_output)

  generated_loss = loss_object(tf.zeros_like(disc_generated_output), disc_generated_output)

  total_disc_loss = real_loss + generated_loss

  return total_disc_loss

# %%
# Cell 25

generator_optimizer = tf.keras.optimizers.Adam(2e-4, beta_1=0.5)
discriminator_optimizer = tf.keras.optimizers.Adam(2e-4, beta_1=0.5)


checkpoint_dir = './training_checkpoints'
checkpoint_prefix = os.path.join(checkpoint_dir, "ckpt")
checkpoint = tf.train.Checkpoint(generator_optimizer=generator_optimizer,
                                 discriminator_optimizer=discriminator_optimizer,
                                 generator=generator,
                                 discriminator=discriminator)

# %%
status = checkpoint.restore(tf.train.latest_checkpoint(checkpoint_dir))

# %%
# Cell 27

def generate_images(model, test_input, tar):
  prediction = model(test_input, training=True)
  plt.figure(figsize=(15,15))

  display_list = [test_input[0], tar[0], prediction[0]]
  title = ['Input Image', 'Ground Truth', 'Predicted Image']

  for i in range(3):
    plt.subplot(1, 3, i+1)
    plt.title(title[i])
    # getting the pixel values between [0, 1] to plot it.
    plt.imshow(display_list[i] * 0.5 + 0.5)
    plt.axis('off')
  plt.show()


# %%
# T1
T1_dataset = tf.data.Dataset.list_files(T1_PATH+'\\*.bmp')
T1_dataset = T1_dataset.map(load_image, num_parallel_calls=tf.data.experimental.AUTOTUNE)
T1_dataset = T1_dataset.batch(1)         


# %%
# T2
T2_dataset = tf.data.Dataset.list_files(T2_PATH+'\\*.bmp')
T2_dataset = T2_dataset.map(load_image, num_parallel_calls=tf.data.experimental.AUTOTUNE)
T2_dataset = T2_dataset.batch(1)

# %% 
T1_list = [t for t in T1_dataset]
T2_list = [t for t in T2_dataset]


# %%
generate_images(generator, T1_list[0], T2_list[0])

# %%
for example_input, example_target in test_dataset.take(1):
  generate_images(generator, example_input, example_target)
# %%
