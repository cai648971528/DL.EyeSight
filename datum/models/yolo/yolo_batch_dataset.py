# Copyright (c) 2009 IW.
# All rights reserved.
#
# Author: liuguiyang <liuguiyangnwpu@gmail.com>
# Date:   2018/3/5

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import random
import cv2
import numpy as np
from queue import Queue
from threading import Thread, Lock

from datum.meta.dataset import DataSet


class YoloDataSet(DataSet):
    """TextDataSet
    process text input file dataset
    text file format:
    image_path xmin1 ymin1 xmax1 ymax1 class1 xmin2 ymin2 xmax2 ymax2 class2
    """

    def __init__(self, common_params, dataset_params):
        super(YoloDataSet, self).__init__(common_params, dataset_params)

        # process params
        self.data_path = str(dataset_params['path'])
        self.width = int(common_params['image_size'])
        self.height = int(common_params['image_size'])
        self.batch_size = int(common_params['batch_size'])
        self.thread_num = int(dataset_params['thread_num'])
        self.max_objects = int(common_params['max_objects_per_image'])

        # record and image_label queue
        self.image_label_queue = Queue(maxsize=100)

        self.record_list = []

        # filling the record_list
        input_file = open(self.data_path, 'r')

        for line in input_file:
            line = line.strip()
            if ',' in line:
                ss = line.split(',')
            else:
                ss = line.split(' ')
            ss[1:] = [float(num) for num in ss[1:]]
            self.record_list.append(ss)

        self.record_point = 0
        self.record_number = len(self.record_list)
        self.record_number_lock = Lock()

        for i in range(self.thread_num):
            t_record_producer = Thread(target=self.record_producer)
            t_record_producer.daemon = True
            t_record_producer.start()

        # for i in range(self.thread_num):
        #     t = Thread(target=self.record_customer)
        #     t.daemon = True
        #     t.start()

    def record_producer(self):
        def update_shuffle():
            if self.record_point % self.record_number == 0:
                random.shuffle(self.record_list)
                self.record_point = 0

        while True:
            outs = list()
            while len(outs) < self.batch_size:
                item = self.record_list[self.record_point]
                out = self.record_process(item)
                outs.append(out)
                self.record_number_lock.acquire()
                self.record_point += 1
                update_shuffle()
                self.record_number_lock.release()

            self.image_label_queue.put(outs)

    # def record_customer(self):
    #     while True:
    #         item = self.record_queue.get()
    #         out = self.record_process(item)
    #         self.image_label_queue.put(out)

    def record_process(self, record):
        """record process
        Args: record
        Returns:
          image: 3-D ndarray
          labels: 2-D list [self.max_objects, 5] (xcenter, ycenter, w, h, class_num)
          object_num:  total object number  int
        """
        image = cv2.imread(record[0])
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h = image.shape[0]
        w = image.shape[1]

        width_rate = self.width * 1.0 / w
        height_rate = self.height * 1.0 / h

        image = cv2.resize(image, (self.height, self.width))

        labels = [[0, 0, 0, 0, 0]] * self.max_objects
        i = 1
        object_num = 0
        while i < len(record):
            xmin = record[i]
            ymin = record[i + 1]
            xmax = record[i + 2]
            ymax = record[i + 3]
            class_num = record[i + 4]

            xcenter = (xmin + xmax) * 1.0 / 2 * width_rate
            ycenter = (ymin + ymax) * 1.0 / 2 * height_rate

            box_w = (xmax - xmin) * width_rate
            box_h = (ymax - ymin) * height_rate

            labels[object_num] = [xcenter, ycenter, box_w, box_h, class_num]
            object_num += 1
            i += 5
            if object_num >= self.max_objects:
                break
        return [image, labels, object_num]

    def batch(self):
        """get batch
        Returns:
          images: 4-D ndarray [batch_size, height, width, 3]
          labels: 3-D ndarray [batch_size, max_objects, 5]
          objects_num: 1-D ndarray [batch_size]
        """
        images = []
        labels = []
        objects_num = []
        outs = self.image_label_queue.get()
        for i in range(self.batch_size):
            image, label, object_num = outs[i][:]
            images.append(image)
            labels.append(label)
            objects_num.append(object_num)

        # for i in range(self.batch_size):
        #     image, label, object_num = self.image_label_queue.get()
        #     images.append(image)
        #     labels.append(label)
        #     objects_num.append(object_num)
        images = np.asarray(images, dtype=np.float32)
        images = images / 255 * 2 - 1
        labels = np.asarray(labels, dtype=np.float32)
        objects_num = np.asarray(objects_num, dtype=np.int32)
        return images, labels, objects_num
