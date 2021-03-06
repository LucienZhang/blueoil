# Training for Keypoint Detection

This tutorial covers training a neural network model on a GPU server to perform keypoint detection.
Specifically, we will train a single-person pose estimation model.

## Preparation

### Dataset

The COCO dataset is available from the official website.
Although COCO dataset is for multi-person pose estimation challenge track.
We customize this dataset to train a single-person pose estimation task.

Blueoil supports 2 formats for keypoint detection.
- MSCOCO format
- YouTube Faces format

For details, please refer to **MSCOCO_2017 keypoint detection** section in <a href="../usage/dataset.html">Prepare training dataset</a>

### Environment variables

For example, if you have prepared MSCOCO_2017 dataset successfully as `/storage/dataset/MSCOCO_2017`.
Export `DATA_DIR` to make sure dataset loader can locate it properly.

    export DATA_DIR=/storage/dataset

Optionally, you can also export `OUTPUT_DIR`. if not, default 
`OUTPUT_DIR` will be `saved/` under blueoil root path.

    export OUTPUT_DIR=/storage/saved

In this tutorial, we assume we have exported both variables as above.

## Generate a configuration file

Note: Below instructions assume your current path is blueoil root path.

Generate your model configuration file interactively by running the `python blueoil/cmd/main.py init` command.

    $ PYTHONPATH=.:lmnet:dlk/python/dlk python blueoil/cmd/main.py init

Below is an example of initialization.

```
#### Generate config ####
your model name ():  keypoint_detection_demo
choose task type  keypoint_detection
choose network  LmSinglePoseV1Quantize
choose dataset format  Mscoco for Single-Person Pose Estimation
training dataset path:  MSCOCO_2017
set validation dataset? (if answer no, the dataset will be separated for training and validation by 9:1 ratio.)  yes
validation dataset path:  MSCOCO_2017
batch size (integer):  4
image size (integer x integer):  160x160
how many epochs do you run training (integer):  100
select optimizer:  Adam
initial learning rate:  0.001
choose learning rate schedule ({epochs} is the number of training epochs you entered before):  '3-step-decay-with-warmup' -> warmup learning rate 1/1000 in first epoch, then train the same way as '3-step-d
enable data augmentation?  Yes
Please choose augmentors:  done (6 selections)
apply quantization at the first layer?  no
```

If configuration finishes, the configuration file is generated in the `{Model name}.yml` under current directory.
It should be `keypoint_detection_demo.yml` if you use above example initialization.


When you wnat to create config yaml in specific filename or directory, you can use `-o` option.

    $ PYTHONPATH=.:lmnet:dlk/python/dlk python blueoil/cmd/main.py init -o ./configs/my_config.yml

## Train a network model

Train your model by running `python blueoil/cmd/main.py train` with a model configuration.
Feel free to replace `keypoint_detection_demo.yml` by your custom config file.

    $ PYTHONPATH=.:lmnet:dlk/python/dlk python blueoil/cmd/main.py train -c keypoint_detection_demo.yml
    
    

When training has started, the training log and checkpoints are generated under `${OUTPUT_DIR}/{Mode name}_{TIMESTAMP}`,
i.e. `/storage/saved/keypoint_detection_demo_{TIMESTAMP}` here.

Training runs on the TensorFlow backend. So you can use TensorBoard to visualize your training process.

    $ tensorboard --logdir=${OUTPUT_DIR}/keypoint_detection_demo_{TIMESTAMP} --port {Port}

- loss / metrics
<img src="../_static/keypoint_detection_scalar.png">

Note: loss consists of global_loss and refine_loss.
global_loss is for all keypoints, refine_loss is for some difficult keypoints.

- input / labels_heatmap / output_heatmap
<img src="../_static/keypoint_detection_heatmap.png">

- visualize_labels, visualize_output
<img src="../_static/keypoint_detection_visualize.png">


## Convert training result to FPGA ready format.

Convert trained model to executable binary files for x86, ARM, and FPGA.
Currently, conversion for FPGA only supports Intel Cyclone® V SoC FPGA.

    $ PYTHONPATH=.:lmnet:dlk/python/dlk python blueoil/cmd/main.py convert -e keypoint_detection_demo_{TIMESTAMP}

`python blueoil/cmd/main.py convert` automatically executes some conversion processes.
- Converts Tensorflow checkpoint to protocol buffer graph.
- Optimizes graph.
- Generates source code for executable binary.
- Compiles for x86, ARM and FPGA.

If conversion is successful, output files are generated under
`/storage/saved/keypoint_detection_demo_{TIMESTAMP}/export/save.ckpt-{Checkpoint No.}/{Image size}/output`.

```
output
├── fpga
│   ├── preloader-mkpimage.bin
│   ├── soc_system.dtb
│   └── soc_system.rbf
├── models
│   ├── lib
│   │   ├── lib_aarch64.so
│   │   ├── lib_arm.so
│   │   ├── libdlk_aarch64.a
│   │   ├── libdlk_arm.a
│   │   ├── libdlk_fpga.a
│   │   ├── libdlk_x86.a
│   │   ├── lib_fpga.so
│   │   ├── lib_x86.so
│   │   ├── lm_aarch64.elf
│   │   ├── lm_arm.elf
│   │   ├── lm_fpga.elf
│   │   └── lm_x86.elf
│   ├── meta.yaml
│   └── minimal_graph_with_shape.pb
├── python
│   ├── lmnet
│   │   ├── common.py
│   │   ├── data_augmentor.py
│   │   ├── data_processor.py
│   │   ├── __init__.py
│   │   ├── nnlib.py
│   │   ├── post_processor.py
│   │   ├── pre_processor.py
│   │   ├── tensorflow_graph_runner.py
│   │   ├── utils
│   │   │   ├── box.py
│   │   │   ├── config.py
│   │   │   ├── demo.py
│   │   │   ├── image.py
│   │   │   ├── __init__.py
│   │   │   └── output.py
│   │   └── visualize.py
│   ├── motion_jpeg_server_from_camera.py
│   ├── README.md
│   ├── requirements.txt
│   ├── run.py
│   └── usb_camera_demo.py
└── README.md
```

## Run inference script on x86 Linux (Ubuntu 16.04)

- Prepare images for inference (not included in the training dataset)

	You can find test imgaes on [Creative Commons](https://ccsearch.creativecommons.org/).
	[Sample](https://ccsearch.creativecommons.org/photos/1a9d20a0-d061-456d-af11-b8753bd46f47)

		$ wget https://live.staticflickr.com/4117/4881737773_0e3ab67b6f_b.jpg

- Run the inference script.

    Explore into the `output/python` directory, and
    run `run.py` and the inference result is saved in `./output/output.json`.

    Note: If you run the script for the first time, you have to setup a python environment (2.7 or 3.5+) and required python packages.

	```
	$ cd {output/python directory}
	$ sudo pip install -r requirements.txt  # for the first time only
	$ python run.py \
	      -i {inference image path} \
	      -m ../models/lib/lib_x86.so \
	      -c ../models/meta.yaml
	```

	*Tips:* The default confidence_threshold for keypoint detection is `0.1`.
	If only a part of a human body is in inference_image, but there are some redundant keypoints visulized.
	Please consider enlarging this value in `output/models/meta.yaml`.

	```
	POST_PROCESSOR:
    - GaussianHeatmapToJoints:
        confidence_threshold: 0.1
	```

- Check inference results. An example output file is shown below.

```
{
    "classes": [
        {
            "id": 0,
            "name": "person"
        }
    ],
    "date": "2019-12-17T08:54:58.835100+00:00",
    "results": [
        {
            "file_path": "4881737773_0e3ab67b6f_b.jpg",
            "prediction": {
                "joints": [
                    308,
                    376,
                    376,
                    274,
                    239,
                    376,
                    274,
                    479,
                    ...
                ]
            }
        }
    ],
    "task": "IMAGE.KEYPOINT_DETECTION",
    "version": 0.2
}
```
