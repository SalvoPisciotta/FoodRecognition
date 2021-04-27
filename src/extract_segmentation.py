from pycocotools.coco import COCO
import numpy as np
import cv2
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

class ExtractSegmentations:

    def __init__(self, pathDir, imgDir='/images/', annotationFile='annotations.json', masksDir='masks/'):
        self.pathDir = pathDir
        self.imgDir = imgDir
        self.annotationFile = annotationFile
        self.masksDir = masksDir
        self.coco = COCO(pathDir+annotationFile)

        # list of category ids adding 0 as first element
        catIds = self.coco.getCatIds()
        catIds.insert(0,0)
        catIds.sort()
        self.catIds = catIds
        self.mapCatIdsLabels = dict(zip(catIds, [i for i in range(len(catIds))]))

    def getCoco(self):
        return self.coco

    def intToRgb(self, value):
        b = value % 256
        g = ((value - b) / 256) % 256
        r = ((value - b) / 256 ** 2) - g / 256
        return np.array([r,g,b],dtype=np.uint8)

    def rgbToInt(self, pixel):
        r = pixel[0]
        g = pixel[1]
        b = pixel[2]
        return 256**2 * r + 256 * g + b;


    def getMultiChannelMasks(self):
        imgIds = self.coco.getImgIds()
        imgs = self.coco.loadImgs(imgIds)

        return [self.loadMask(img['id']) for img in imgs]



    def loadMask(self, imgId):
        """Generate instance masks for an image.
       Returns:
        masks: A bool array of shape [height, width, instance count] with
            one mask per instance.
        class_ids: a 1D array of class IDs of the instance masks.
        """

        img = self.coco.loadImgs(imgId)[0]

        # load all annotations for the given image
        anns = self.coco.getAnnIds(imgIds=imgId)
        instance_count = len(anns)


        # array of class IDs of each instance
        class_ids = list()

        # Convert annotations to a bitmap mask of shape [height, width, instance_count]
        mask = np.zeros((img['height'], img['width'], instance_count), dtype=np.uint8)

        for i, ann in enumerate(anns):
            ann = self.coco.loadAnns(ann)[0]
            mask[:, :, i] = np.array(self.coco.annToMask(ann), dtype=np.uint8)

            class_ids.append(ann['category_id'])

        # Return mask, and array of class IDs of each instance. Since we have
        # one class ID only, we return an array of 1s
        # Map class names to class IDs.
        return mask, class_ids



    def extractMasks(self):
        imgIds = self.coco.getImgIds()
        imgs = self.coco.loadImgs(imgIds)

        masks = list()

        for img in imgs:
            anns = self.coco.getAnnIds(imgIds=img['id'])

            mask = np.zeros((img['height'], img['width']), dtype=np.uint16)
            for ann in anns:
                ann = self.coco.loadAnns(ann)[0]
                catId = ann['category_id']
                mask += (np.array(self.coco.annToMask(ann), dtype=np.uint16)*catId)

            cv2.imwrite(self.pathDir + self.masksDir + img["file_name"], mask)
            masks.append(mask)
        return masks


    def extractBinaryMasks(self):
        imgIds = self.coco.getImgIds()
        imgs = self.coco.loadImgs(imgIds)

        masks = list()

        for img in imgs:
            anns = self.coco.getAnnIds(imgIds=img['id'])

            mask = np.zeros((img['height'], img['width']), dtype=np.uint8)
            for ann in anns:
                ann = self.coco.loadAnns(ann)[0]
                mask = np.bitwise_or(mask, np.array(self.coco.annToMask(ann),  dtype=np.uint8))     # bit or

            cv2.imwrite(self.pathDir + self.masksDir + img["file_name"], mask)
            masks.append(mask)
        return masks


    def showBinaryMasks(self, n=4):
        image_ids = np.random.choice(self.coco.getImgIds(), n)
        imgs_json = self.coco.loadImgs(image_ids)

        for json in imgs_json:
            img = mpimg.imread(self.pathDir+self.imgDir + json['file_name'])
            mask = mpimg.imread(self.pathDir+self.masksDir + json['file_name'])

            # plot images
            fig, axes = plt.subplots(figsize=(10, 5), nrows=1, ncols=2)
            ax = axes.flat

            ax[0].imshow(img)
            ax[0].axis('off')

            ax[1].imshow(mask * 255)
            ax[1].axis('off')

            fig.tight_layout()

            plt.show()






