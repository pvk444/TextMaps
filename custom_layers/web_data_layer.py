import os
import cv2
import yaml
import json
import caffe
import pickle
import logging
import numpy as np
import matplotlib.pyplot as plt
from multiprocessing import Process, Queue
from sklearn.preprocessing import normalize


IMAGES_PATH='/storage/plzen1/home/gogartom/TextMaps/data_shops/images/'
TEXT_MAPS_PATH='/storage/plzen1/home/gogartom/TextMaps/data_shops/text_maps/'
BOXES_PATH='/storage/plzen1/home/gogartom/TextMaps/data_shops/input_boxes/'

class WebDataLayer(caffe.Layer):

    def start_fetcher(self):
        self.prefetch_process = DataFetcher(self.queue, self.data, self.batch_size, self.phase,
                                            self.x_size, self.y_size, self.text_map_scale, self.im_scale)
        self.prefetch_process.daemon = True
        self.prefetch_process.start()

        # Terminate the child process when the parent exists
        def cleanup():
            print 'Terminating DataFetcher'
            self.prefetch_process.terminate()
            self.prefetch_process.join()
        import atexit
        atexit.register(cleanup)

    def load_data_set(self,path):
        with(open(path,'r')) as f:
            data = [line.strip() for line in f.readlines()]
            return data


    def matrix_list_to_blob(self, ims):
        max_shape = np.array([im.shape for im in ims]).max(axis=0)
        num_images = len(ims)
        blob = np.zeros((num_images, max_shape[0], max_shape[1], 1),
                    dtype=np.float32)

        for i in xrange(num_images):
            im = ims[i]
            blob[i, 0:im.shape[0], 0:im.shape[1], 0] = im

        blob = blob.transpose((0, 3, 1, 2))
        return blob


    def tensor_list_to_blob(self, ims):
        max_shape = np.array([im.shape for im in ims]).max(axis=0)       
        n_channels = ims[0].shape[2]
        
        num_images = len(ims)
        blob = np.zeros((num_images, max_shape[0], max_shape[1], n_channels),
                    dtype=np.float32)
       
        for i in xrange(num_images):
            im = ims[i]
            blob[i, 0:im.shape[0], 0:im.shape[1], :] = im
 
        blob = blob.transpose((0, 3, 1, 2))
        return blob

    def setup(self, bottom, top):
        ### READ PARAMS        
        layer_params = yaml.load(self.param_str)
        self.data_set_path = layer_params['data']
        self.phase = layer_params['phase']

        if self.phase == 'TEST':
            self.batch_size = 1
        else:
            self.batch_size = layer_params['batch_size']

        ### INPUT PARAMS
        self.y_size = 1280
        self.x_size = 1280

        self.text_map_scale = layer_params['txt_scale']
        self.im_scale = layer_params['im_scale']

        self.data = self.load_data_set(self.data_set_path)
        self.prefetch_process = None
        self.queue = Queue(10)

        # image
        top[0].reshape(self.batch_size, 3, int(round(self.y_size*self.im_scale)), int(round(self.x_size*self.im_scale)))
        # text map
        top[1].reshape(self.batch_size, 128,int(round(self.y_size*self.text_map_scale)), int(round(self.x_size*self.text_map_scale)))

        # boxes
        top[2].reshape(200,5)

        # label
        top[3].reshape(200,)

    def reshape(self, bottom, top):
        pass

    def forward(self, bottom, top):
        
        ### CHECK PREFETCHING THREAD AND START
        if not self.prefetch_process:
            self.start_fetcher()

        ### GET DATA FROM QUEUE
        blobs = self.queue.get()

        im_blob = blobs[0]
        text_blob = blobs[1]
        boxes_blob = blobs[2]
        labels_blob = blobs[3]

        ### RESHAPE
        top[0].reshape(*(im_blob.shape))
        top[1].reshape(*(text_blob.shape))
        top[2].reshape(*(boxes_blob.shape))
        top[3].reshape(*(labels_blob.shape))

        ### SET DATA      
        top[0].data[...] = im_blob
        top[1].data[...] = text_blob
        top[2].data[...] = boxes_blob
        top[3].data[...] = labels_blob

    def backward(self, top, propagate_down, bottom):
        pass

class DataFetcher(Process):

    def get_minibatch(self, data):
        images = []
        text_maps = []
        boxes_blob = np.zeros((0, 5), dtype=np.float32)
        labels_blob = np.zeros((0), dtype=np.float32)

        ### for each page in batch
        for i in range(len(data)):
            ### IMAGE
            image_path=os.path.join(IMAGES_PATH, data[i]+'.jpeg')
            im = self.load_image(image_path)
            images.append(im)

            ### TEXT MAP
            text_path=os.path.join(TEXT_MAPS_PATH,data[i]+'.pkl')
            text_map = self.load_text_map(text_path)
            text_maps.append(text_map)

            ### BOXES AND LABELS
            boxes_path=os.path.join(BOXES_PATH,data[i]+'.pkl')
            boxes, labels = self.load_boxes(boxes_path, self.boxes_per_batch)
            batch_ind = i * np.ones((boxes.shape[0], 1))
            boxes_this_image = np.hstack((batch_ind, boxes))
            boxes_blob = np.vstack((boxes_blob, boxes_this_image))
                
            labels_blob = np.hstack((labels_blob, labels))


        ### create blobs
        im_blob = self.tensor_list_to_blob(images)
        text_blob = self.tensor_list_to_blob(text_maps)

        return im_blob, text_blob, boxes_blob, labels_blob

    def matrix_list_to_blob(self, ims):
        max_shape = np.array([im.shape for im in ims]).max(axis=0)
        num_images = len(ims)
        blob = np.zeros((num_images, max_shape[0], max_shape[1], 1),
                    dtype=np.float32)

        for i in xrange(num_images):
            im = ims[i]
            blob[i, 0:im.shape[0], 0:im.shape[1], 0] = im

        blob = blob.transpose((0, 3, 1, 2))
        return blob

    def tensor_list_to_blob(self, ims):
        max_shape = np.array([im.shape for im in ims]).max(axis=0)
        n_channels = ims[0].shape[2]

        num_images = len(ims)
        blob = np.zeros((num_images, max_shape[0], max_shape[1], n_channels),
                    dtype=np.float32)

        for i in xrange(num_images):
            im = ims[i]
            blob[i, 0:im.shape[0], 0:im.shape[1], :] = im
 
        blob = blob.transpose((0, 3, 1, 2))
        return blob

    def load_image(self, filename):
        im = cv2.imread(filename)

        size_x = min(im.shape[1],self.x_size)
        size_y = min(im.shape[0],self.y_size)

        # Crop
        im_croped = np.zeros((self.y_size,self.x_size,3),dtype=np.uint8)
        im_croped[:size_y,:size_x,:] = im[:size_y,:size_x,:] 

        # in TRAIN phase
        if self.phase == 'TRAIN':
            # Change HUE randomly
            hsv = cv2.cvtColor(im_croped, cv2.COLOR_BGR2HSV) 
            add_value = np.random.randint(low=0,high=180,size=1)[0]
            add_matrix = np.ones(hsv.shape[0:2],dtype=np.uint8)*add_value
            hsv2 = hsv
            hsv2[:,:,0] += add_matrix
            im_croped = cv2.cvtColor(hsv2, cv2.COLOR_HSV2BGR)

            # With probability 15 percent invert image
            invert_ratio = 0.15
            if np.random.uniform() < invert_ratio:
                im_croped = (255-im_croped)

        # Scale
        im_scaled = cv2.resize(im_croped, (0,0), fx=self.im_scale, fy=self.im_scale)
        return im_scaled

    def load_boxes(self, boxes_filename, size):
        n_others = size - 3

        # load data
        with open(boxes_filename,'rb') as f:
            boxes = pickle.load(f)

        gt_boxes = boxes['gt_boxes']
        other_boxes = boxes['other_boxes']
        
        # remove boxes
        #indices_to_remove = []
        #for box in gt_boxes:
        #    ind = np.where(np.all(all_boxes==box,axis=1))[0][0]
        #    indices_to_remove.append(ind)
        #
        #all_boxes = np.delete(all_boxes, indices_to_remove, axis = 0)

        # create boxes
        if self.phase == 'TRAIN':
            rows_to_include=np.random.randint(other_boxes.shape[0],size=n_others)
            other_boxes = other_boxes[rows_to_include,:]
        #elif self.phase == 'TEST':
        #    other_boxes = other_boxes

        boxes = np.vstack((gt_boxes,other_boxes))
        
        # labels
        gt_labels = np.asarray(range(1,4))
        other_labels = np.zeros((other_boxes.shape[0]), dtype = np.float32)
        labels = np.hstack((gt_labels,other_labels))

        return boxes, labels

    def load_text_map(self, filename):
        with open(filename,'rb') as f:
            obj = pickle.load(f)

        shape = obj['shape']
        text_nodes = obj['text_nodes']        

        # specify size
        map_shape = [round(x*self.text_map_scale) for x in [self.y_size,self.x_size]]
        n_features = shape[2]

        features = np.zeros((map_shape[0],map_shape[1],n_features), dtype=np.float)
        for node in text_nodes:
            bb = node[0]
            bb_scaled = [int(round(x*self.text_map_scale)) for x in bb]
            encoded_text = node[1]
            encoded_text = normalize(encoded_text, axis=1, norm='l2')*255
            vector = np.asarray(encoded_text.todense())[0]
            features[bb_scaled[1]:bb_scaled[3],bb_scaled[0]:bb_scaled[2],:] = vector

        # HIDE ELEMENTS
        #if hide_rois_elements:
        #    for elem in hide_rois_elements:
        #        sc_elem = [round(e*scale) for e in elem]
        #        features[sc_elem[1]:sc_elem[3],sc_elem[0]:sc_elem[2],:] = 0

        return features

    def __init__(self, queue, data, batch_size, phase, x_size, y_size, text_map_scale, im_scale):
        super(DataFetcher, self).__init__()
        self.queue = queue
        self.data = data
        self.batch_size = batch_size
        self.boxes_per_batch = 100
        self.phase = phase

        self.x_size = x_size
        self.y_size = y_size
        self.text_map_scale = text_map_scale
        self.im_scale = im_scale

        np.random.seed(1)
        self.shuffle_data()

    def shuffle_data(self):
        self.perm = np.random.permutation(np.arange(len(self.data)))
        self.cursor = 0

    def get_next_minibatch_inds(self):
        if self.cursor + self.batch_size >= len(self.data):
            self.shuffle_data()

        indices = self.perm[self.cursor:self.cursor + self.batch_size]
        self.cursor += self.batch_size
        return indices

    def run(self):
        print 'DataFetcher started'
        while True:
            indices = self.get_next_minibatch_inds()
            minibatch_data = [self.data[i] for i in indices]
            blobs = self.get_minibatch(minibatch_data)
            self.queue.put(blobs)

if __name__ == "__main__":
    pass