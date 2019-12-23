import tensorflow as tf
import keras
import keras.layers as KL
from keras.callbacks import LearningRateScheduler, TensorBoard, ModelCheckpoint
from keras.preprocessing.image import ImageDataGenerator
import numpy as np

# Requires TensorFlow 1.3+ and Keras 2.0.8+.
from distutils.version import LooseVersion

assert LooseVersion(tf.__version__) >= LooseVersion("1.3")
assert LooseVersion(keras.__version__) >= LooseVersion('2.0.8')

import functools
from lmnet.quantizations import (
    binary_mean_scaling_quantizer,
)
from lmnet.networks.instance_segmentation.keras_linear import linear_mid_tread_half_quantizer

#####################
# QUANTIZE
#####################

ACTIVATION_QUANTIZER = linear_mid_tread_half_quantizer
ACTIVATION_QUANTIZER_KWARGS = {
    'bit': 2,
    'max_value': 2
}
WEIGHT_QUANTIZER = binary_mean_scaling_quantizer
WEIGHT_QUANTIZER_KWARGS = {}


#####################
# QUANTIZE
#####################

def quantized_variable_getter(getter, name, weight_quantization=None, *args, **kwargs):
    """Get the quantized variables.
    Use if to choose or skip the target should be quantized.
    Args:
        getter: Default from tensorflow.
        name: Default from tensorflow.
        weight_quantization: Callable object which quantize variable.
        args: Args.
        kwargs: Kwargs.
    """
    assert callable(weight_quantization)
    var = getter(name, *args, **kwargs)
    with tf.compat.v1.variable_scope(name):
        # Apply weight quantize to variable whose last word of name is "kernel".
        if "kernel" == var.op.name.split("/")[-1]:
            return weight_quantization(var)
    return var


my_activation = ACTIVATION_QUANTIZER(**ACTIVATION_QUANTIZER_KWARGS)
my_activation = KL.Activation(my_activation)
weight_quantization = WEIGHT_QUANTIZER(**WEIGHT_QUANTIZER_KWARGS)
my_custom_getter = functools.partial(quantized_variable_getter,
                                     weight_quantization=weight_quantization)


############################################################
#  Resnet Graph
############################################################

class BatchNorm(KL.BatchNormalization):
    """Extends the Keras BatchNormalization class to allow a central place
    to make changes if needed.

    Batch normalization has a negative effect on training if batches are small
    so this layer is often frozen (via setting in Config class) and functions
    as linear layer.
    """

    def call(self, inputs, training=None):
        """
        Note about training values:
            None: Train BN layers. This is the normal mode
            False: Freeze BN layers. Good when batch size is small
            True: (don't use). Set layer in training mode even when making inferences
        """
        return super(self.__class__, self).call(inputs, training=training)


def identity_block_18(input_tensor, kernel_size, filters, stage, block,
                      use_bias=True, train_bn=True, config=None):
    """The identity_block is the block that has no conv layer at shortcut
    # Arguments
        input_tensor: input tensor
        kernel_size: default 3, the kernel size of middle conv layer at main path
        filters: list of integers, the nb_filters of 3 conv layer at main path
        stage: integer, current stage label, used for generating layer names
        block: 'a','b'..., current block label, used for generating layer names
        use_bias: Boolean. To use or not use a bias in conv layers.
        train_bn: Boolean. Train or freeze Batch Norm layers
    """
    nb_filter1, nb_filter2 = filters
    conv_name_base = 'res' + str(stage) + block + '_branch'
    bn_name_base = 'bn' + str(stage) + block + '_branch'

    with tf.compat.v1.variable_scope('quantize_group_' + str(stage) + block, custom_getter=my_custom_getter):
        x = KL.Conv2D(nb_filter1, (kernel_size, kernel_size), padding='same',
                      name=conv_name_base + '2a', use_bias=use_bias)(input_tensor)
        x = BatchNorm(name=bn_name_base + '2a')(x, training=train_bn)
        x = my_activation(x)

        x = KL.Conv2D(nb_filter2, (1, 1), name=conv_name_base + '2b',
                      use_bias=use_bias)(x)
    x = BatchNorm(name=bn_name_base + '2b')(x, training=train_bn)

    x = KL.Add()([x, input_tensor])
    x = my_activation(x)
    return x


def conv_block_18(input_tensor, kernel_size, filters, stage, block,
                  strides=(2, 2), use_bias=True, train_bn=True, config=None):
    """conv_block is the block that has a conv layer at shortcut
    # Arguments
        input_tensor: input tensor
        kernel_size: default 3, the kernel size of middle conv layer at main path
        filters: list of integers, the nb_filters of 3 conv layer at main path
        stage: integer, current stage label, used for generating layer names
        block: 'a','b'..., current block label, used for generating layer names
        use_bias: Boolean. To use or not use a bias in conv layers.
        train_bn: Boolean. Train or freeze Batch Norm layers
    Note that from stage 3, the first conv layer at main path is with subsample=(2,2)
    And the shortcut should have subsample=(2,2) as well
    """
    nb_filter1, nb_filter2 = filters
    conv_name_base = 'res' + str(stage) + block + '_branch'
    bn_name_base = 'bn' + str(stage) + block + '_branch'

    with tf.compat.v1.variable_scope('quantize_group_' + str(stage) + block, custom_getter=my_custom_getter):
        x = KL.MaxPooling2D((1, 1), strides=strides)(input_tensor)
        x = KL.Conv2D(nb_filter1, (kernel_size, kernel_size), padding='same',
                      name=conv_name_base + '2a', use_bias=use_bias)(x)
        x = BatchNorm(name=bn_name_base + '2a')(x, training=train_bn)
        x = my_activation(x)

        x = KL.Conv2D(nb_filter2, (1, 1), name=conv_name_base + '2b', use_bias=use_bias)(x)
        x = BatchNorm(name=bn_name_base + '2b')(x, training=train_bn)

        shortcut = KL.Conv2D(nb_filter2, (1, 1), strides=strides,
                             name=conv_name_base + '1', use_bias=use_bias)(input_tensor)
        shortcut = BatchNorm(name=bn_name_base + '1')(shortcut, training=train_bn)

        x = KL.Add()([x, shortcut])
        x = my_activation(x)
    return x


def resnet_graph_18(input_image, train_bn=True, config=None):
    """Build a ResNet graph.
        architecture: Can be resnet50 or resnet101
        stage5: Boolean. If False, stage5 of the network is not created
        train_bn: Boolean. Train or freeze Batch Norm layers
    """
    # Stage 1
    x = KL.ZeroPadding2D((3, 3))(input_image)
    x = KL.Conv2D(64, (7, 7), strides=(2, 2), name='conv1', use_bias=True)(x)
    x = BatchNorm(name='bn_conv1')(x, training=train_bn)
    x = my_activation(x)
    C1 = x = KL.MaxPooling2D((3, 3), strides=(2, 2), padding="same")(x)
    # Stage 2
    x = conv_block_18(x, 3, [64, 256], stage=2, block='a', strides=(1, 1), train_bn=train_bn, config=config)
    C2 = x = identity_block_18(x, 3, [64, 256], stage=2, block='b', train_bn=train_bn, config=config)
    # Stage 3
    x = conv_block_18(x, 3, [128, 512], stage=3, block='a', train_bn=train_bn, config=config)
    C3 = x = identity_block_18(x, 3, [128, 512], stage=3, block='b', train_bn=train_bn, config=config)
    # Stage 4
    x = conv_block_18(x, 3, [256, 1024], stage=4, block='a', train_bn=train_bn, config=config)
    C4 = x = identity_block_18(x, 3, [256, 1024], stage=4, block='b', train_bn=train_bn, config=config)
    # Stage 5
    x = conv_block_18(x, 3, [512, 2048], stage=5, block='a', train_bn=train_bn, config=config)
    C5 = x = identity_block_18(x, 3, [512, 2048], stage=5, block='b', train_bn=train_bn, config=config)
    return x, C1, C2, C3, C4, C5


# TODO: this should be placed in utils
def random_crop(img, random_crop_size):
    # Note: image_data_format is 'channel_last'
    assert img.shape[2] == 3
    height, width = img.shape[0], img.shape[1]
    dy, dx = random_crop_size
    x = np.random.randint(0, width - dx + 1)
    y = np.random.randint(0, height - dy + 1)
    return img[y:(y + dy), x:(x + dx), :]


def crop_generator(batches, crop_length):
    """Take as input a Keras ImageGen (Iterator) and generate random
    crops from the image batches generated by the original iterator.
    """
    while True:
        batch_x, batch_y = next(batches)
        batch_crops = np.zeros((batch_x.shape[0], crop_length, crop_length, 3))
        for i in range(batch_x.shape[0]):
            batch_crops[i] = random_crop(batch_x[i], (crop_length, crop_length))
        yield (batch_crops, batch_y)


def val_gen():
    # TODO(lucien): hard coding
    gt_file = '/storage/dataset/ILSVRC2012/val.txt'
    val_dir = '/storage/dataset/ILSVRC2012/val/'
    with open(gt_file, 'r') as f:
        while True:
            batch_input = np.zeros((BATCH_SIZE, 224, 224, 3), dtype='float32')
            batch_output = np.zeros((BATCH_SIZE,))
            for line, idx in zip(f, range(BATCH_SIZE)):
                image_name, label = line.strip().split()
                image = keras.preprocessing.image.load_img(val_dir + image_name, target_size=(224, 224))
                image = np.array(image, 'float32')
                image /= 255.
                image = (image - mean) / std
                batch_input[idx] = image
                batch_output[idx] = int(label)
                batch_output = keras.utils.to_categorical(batch_output, num_classes=1000)
            yield (batch_input, batch_output)


if __name__ == '__main__':
    ##############
    # Model
    ##############

    input_image = KL.Input(shape=[None, None, 3], name="input_image")

    x, _, _, _, _, _ = resnet_graph_18(input_image, train_bn=True, config=None)

    x = KL.GlobalAveragePooling2D(name='global_avg_pool')(x)
    outputs = KL.Dense(1000, activation='softmax', name='fc1000')(x)

    model = keras.Model(input_image, outputs, name='resnet18')

    # TODO(lucien): hard coding
    log_dir = '/home/zhang/blueoil/lmnet/lmnet/networks/instance_segmentation/logs/'
    data_dir = '/storage/dataset/ILSVRC2012/'

    BATCH_SIZE = 128
    mean = [0.485, 0.456, 0.406]  # rgb
    std = [0.229, 0.224, 0.225]

    train_gen = ImageDataGenerator(rescale=1 / 255.,
                                   width_shift_range=0.125,
                                   height_shift_range=0.125,
                                   fill_mode='constant',
                                   cval=0.,
                                   horizontal_flip=True,
                                   dtype='float32',
                                   preprocessing_function=lambda image: (image - mean) / std)
    train_data = train_gen.flow_from_directory(data_dir + 'train', target_size=(256, 256), class_mode='categorical',
                                               batch_size=BATCH_SIZE)

    train_data = crop_generator(train_data, 224)

    model.compile(loss='categorical_crossentropy', metrics=['accuracy'],
                  optimizer=keras.optimizers.SGD(0.1, 0.9, nesterov=True))

    START_LR = 0.1
    BASE_LR = START_LR * (BATCH_SIZE / 256.0)


    def scheduler(epoch):
        if epoch < 30:
            return min(START_LR, BASE_LR)
        elif epoch < 60:
            return BASE_LR * 1e-1
        elif epoch < 90:
            return BASE_LR * 1e-2
        elif epoch < 100:
            return BASE_LR * 1e-3
        else:
            return BASE_LR * 1e-4


    change_lr = LearningRateScheduler(scheduler)
    tb_cb = TensorBoard(log_dir=log_dir, histogram_freq=0)
    # ckpt_cb = ModelCheckpoint(filepath=str(log_dir / '{epoch:02d}.hdf5'), monitor='val_acc', save_weights_only=True,
    #                           period=50)
    callbacks = [change_lr, tb_cb]

    EPOCHS = 150

    model.fit_generator(train_data,
                        epochs=EPOCHS,
                        callbacks=callbacks,
                        steps_per_epoch=1281167 // BATCH_SIZE,
                        validation_data=val_gen
                        )

    model.save(log_dir)
