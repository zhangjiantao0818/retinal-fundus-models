from __future__ import annotations

import math

import keras
import numpy as np
import pandas as pd
import skimage.io
import skimage.transform

from bsmu.retinal_fundus.models.utils import debug as debug_utils
from bsmu.retinal_fundus.models.utils import image as image_utils


class DataGenerator(keras.utils.Sequence):
    def __init__(self, config: ModelTrainerConfig, data_csv_path: Path, shuffle: bool, augmentation_transforms,
                 discard_last_incomplete_batch: bool = True):
        self.config = config
        self.shuffle = shuffle
        self.augmentation_transforms = augmentation_transforms
        self.discard_last_incomplete_batch = discard_last_incomplete_batch

        data_frame = pd.read_csv(str(data_csv_path))
        data = data_frame.to_numpy()
        self.sample_qty = len(data)

        self.images = np.empty(
            shape=(self.sample_qty, *self.config.model_input_image_shape()), dtype=np.float32)
        self.masks = np.empty_like(self.images)

        for index, data_row in enumerate(data):
            image_id = data_row[0]
            print(f'#{index + 1}/{self.sample_qty} \timage_id: {image_id}')

            image_path = self.config.image_dir() / image_id
            image = skimage.io.imread(str(image_path))
            image = skimage.transform.resize(
                image, self.config.model_input_image_shape(), order=3, anti_aliasing=True)  # preserve_range=True)
            image = image_utils.normalized_image(image).astype(np.float32)
            self.images[index] = image

            mask_path = self.config.mask_dir() / image_id
            mask = skimage.io.imread(str(mask_path))
            mask = skimage.transform.resize(
                mask, self.config.model_input_image_shape(), order=3, anti_aliasing=True)  # preserve_range=True)
            mask = image_utils.normalized_image(mask).astype(np.float32)
            self.masks[index] = mask

        debug_utils.print_info(self.images, 'images')
        debug_utils.print_info(self.masks, 'masks')

        self.sample_indexes = np.arange(self.sample_qty)
        self.on_epoch_end()

    def __len__(self):
        """Return number of batches per epoch"""
        batch_qty = self.sample_qty / self.config.BATCH_SIZE
        return math.floor(batch_qty) if self.discard_last_incomplete_batch else math.ceil(batch_qty)

    def __getitem__(self, batch_index):
        """Generate one batch of data"""
        batch_images = np.zeros(shape=self.config.model_input_batch_shape(), dtype=np.float32)
        batch_masks = np.zeros_like(batch_images)

        # Generate image indexes of the batch
        batch_sample_indexes = self.sample_indexes[batch_index * self.config.BATCH_SIZE:
                                                   (batch_index + 1) * self.config.BATCH_SIZE]

        for item_number, batch_sample_index in enumerate(batch_sample_indexes):
            image = self.images[batch_sample_index]
            mask = self.masks[batch_sample_index]

            if self.augmentation_transforms is not None:
                image, mask = augmentate_image_mask(image, mask, self.augmentation_transforms)

                # Normalize once again image to [0, 1] after augmentation
                image = image_utils.normalized_image(image)
                mask = image_utils.normalized_image(mask)

            image = image * 255
            batch_images[item_number, ...] = image

            batch_masks[item_number, ...] = mask

        if self.config.PREPROCESS_BATCH_IMAGES is not None:
            batch_images = self.config.PREPROCESS_BATCH_IMAGES(batch_images)

        return batch_images, batch_masks

    def on_epoch_end(self):
        """Shuffle files after each epoch"""
        if self.shuffle:
            np.random.shuffle(self.sample_indexes)


def augmentate_image_mask(image, mask, augmentation_transforms):
    augmentation_results = augmentation_transforms(image=image, mask=mask)
    return augmentation_results['image'], augmentation_results['mask']