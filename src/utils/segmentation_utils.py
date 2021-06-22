from pycocotools.coco import COCO
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import matplotlib.patches as mpatches
import matplotlib.cm as cm
import os
from PIL import Image

from tensorflow.keras.preprocessing.image import load_img
from tensorflow.keras.preprocessing.image import img_to_array
from tensorflow.keras.utils import Progbar
from keras.preprocessing.image import ImageDataGenerator


def load_coco_dataset(path_dir, annotation_file='annotations.json'):
    """
    Load COCO object reading info about the COCO annotations

    Parameters
    ----------
    path_dir : str
        The directory containing the annotations file
    annotation_file : str
        Filename of the annotations file

    Returns
    -------
    object
        COCO object containing info about the COCO annotations
    """
    return COCO(os.path.join(path_dir, annotation_file))


def load_data(coco, img_dir, img_size, class_names=[],  show_progress=True):
    """
    Load the whole dataset in one shot, filtering it for some categories

    Parameters
    ----------
    coco: object
        COCO object containing info about the COCO annotations
    img_dir: str
        The path to the directory containing images to read
    img_size: tuple
        Height and width according to resize the images
    class_names: list, optional
        List of categories according to filter the dataset. If empty, load all dataset
    show_progress: bool, optional
        If True, it allows to show the progress of the loading

    Returns
    ----------
    tuple
        (x, y) where the first element is a np.array of input image
        and the second element is a np.array of binary masks
    """

    # load images info from annotations
    img_ids, img_names, class_names, cat_to_class = load_imgs(coco, class_names)

    # prepare structure of input images
    x = np.zeros((len(img_names),) + img_size + (3,), dtype=np.float32)

    if show_progress:
        print("Loading images:")
        bar_img = Progbar(target=len(img_names))

    for i, filename in enumerate(img_names):
        path = os.path.join(img_dir, filename)
        img = img_to_array(load_img(path, target_size=img_size))
        x[i] = img

        if show_progress:
            bar_img.update(i)

    # prepare structure of target masks
    y = np.zeros((len(img_names),) + img_size + (len(class_names),), dtype=np.float32)

    if show_progress:
        print("\nLoading masks:")
        bar_mask = Progbar(target=len(img_ids))

    for i, img_id in enumerate(img_ids):
        mask = load_mask(coco, img_id, cat_to_class)

        # scale down mask
        mask_scaled = np.zeros(img_size + (len(class_names),), dtype=np.uint8)
        for j in range(len(class_names)):
            mask_scaled[:, :, j] = Image.fromarray(mask[:, :, j]).resize(img_size, Image.NEAREST)

        y[i] = np.array(mask_scaled, dtype=np.float32)

        if show_progress:
            bar_mask.update(i)
    return x, y


def load_imgs(coco, class_names=[]):
    """
    Load image names and filter the dataset according to the list of categories specified.

    Parameters
    ----------
    coco: object
        COCO object containing info about the COCO annotations
    class_names: list, optional
        List of categories according to filter the dataset. If empty, load all dataset

    Returns
    -------
    tuple
        Tuple composed by:
         - a list of image ids
         - a list of  image names
         - the new list of categories ordered and with the special category 'background' added
         - a dict that maps category ids to the index of the previous array
    """

    # get cat ids
    if class_names is None:
        class_names = []
    cat_ids = coco.getCatIds(catNms=class_names)

    # get cat_names ordered and with the special category 'background'
    cats = coco.loadCats(cat_ids)
    class_names = ['background'] +[cat['name'] for cat in cats]

    # build a map from cat_ids to to the corresponded index of cat_names
    cat_to_class = dict(zip([0] + cat_ids, range(len(class_names))))

    # get images annotated with the filtered categories
    img_ids = [coco.getImgIds(catIds=[id]) for id in cat_ids]

    # List of lists flattening and remove duplicates
    img_ids = list(set([item for sublist in img_ids for item in sublist]))
    img_names = [coco.loadImgs(img_id)[0]['file_name'] for img_id in img_ids]

    return img_ids, img_names, class_names, cat_to_class


def load_mask(coco, img_id, cat_to_class):
    """
    Generate a multichannel mask for an image.

    Parameters
    ----------
    coco: object
        coco object containing info about the COCO annotations
    img_id: int
        id of the image for which you want get the mask
    cat_to_class: dict
        Map from cat_ids to to the corresponded index of class_names

    Returns
    -------
    A np.array of shape [height, width, n_classes] where each channel is a binary mask correspondent to each category.
    The first channel is dedicated to the background
    """

    img = coco.loadImgs(img_id)[0]

    # load all annotations for the given image
    anns = coco.getAnnIds(imgIds=img_id)

    # number of categories according to generate the mask. The background must be included
    n_classes = len(cat_to_class)

    # Convert annotations to a binary mask of shape [height, width, n_classes]
    mask = np.zeros((img['height'], img['width'], n_classes), dtype=np.float32)

    # channel dedicated to the background
    background = np.zeros((img['height'], img['width']), dtype=np.uint8)

    for ann in anns:
        ann = coco.loadAnns(ann)[0]

        # check if it is a considered category
        if ann['category_id'] in list(cat_to_class.keys()):

            # get channel to fill
            i = cat_to_class[ann['category_id']]
            mask[:, :, i] = np.array(coco.annToMask(ann), dtype=np.float32)

            # compose incrementally the background channel
            background = np.bitwise_or(background, coco.annToMask(ann))

    # invert background to set the background as 1 wherever all other mask are 0
    background = np.logical_not(background).astype(int)
    mask[:, :, 0] = np.array(background, dtype=np.float32)

    return mask


def augment(x, y, img_aug_args):
    """
    Generative function that create a batch of augmented images and masks
    for the passed set of images and their correspondent masks.

    Parameters
    ----------
    x : np.array
        Batch of input images
    y : np.array
        Batch of masks
    img_aug_args: dict
        Parameters of the Keras ImageDataGenerator class
    Returns
    ----------
    tuple
        (x, y) of the same shape of the input ones, but transformed
    """

    # the brightness parameter is unuseful for the mask, remove it
    if img_aug_args.keys().__contains__('brightness_range'):
        img_aug_args.pop('brightness_range', None)

    # we apply data augmentation to our datasets using Keras ImageDataGenerator class
    image_aug = ImageDataGenerator(**img_aug_args)

    # transpose the batch of the masks to iter over the channels
    y_t = y.transpose((3, 0, 1, 2))

    # prepare data structure for the augmentation result
    x_aug = np.zeros(x.shape, dtype=np.float32)
    y_aug = np.zeros(y_t.shape, dtype=np.float32)

    # seed useful to sync the augmentation fof x and y applying the same transformation
    seed = np.random.choice(range(9999))

    batch_size = x.shape[0]
    n_channel = y.shape[3]

    # create a generator that can return an augmented batch of images
    image_gen = image_aug.flow(x, batch_size=batch_size, shuffle=False, seed=seed)

    mask_gen = []
    for i in range(n_channel):
        # create a generator that can return an augmented batch of masks
        mask_gen.append(image_aug.flow(y_t[i].reshape(y_t[i].shape + (1,)), shuffle=False, batch_size=batch_size, seed=seed))

    # get the augmented batch
    x_aug = image_gen.next()
    for i in range(n_channel):
        y_aug[i] = mask_gen[i].next()[:,:,:,0]

    return x_aug, np.round(y_aug.transpose((1, 2, 3, 0)))


def get_class_dist(coco, class_names=[]):
    """
    Compute the distibution of the given categories in the dataset

    Parameters
    ----------
    coco: object
        COCO object containing info about the COCO annotations
    class_names: list, optional
        List of categories according to filter the dataset. If empty, load all dataset

    Returns
    -------
    dict
        Dict of cat_id and the corresponding count
    """

    # get cat ids
    if class_names is None:
        class_names = []
    cat_ids = coco.getCatIds(catNms=class_names)

    # get the number of images in the dataset
    img_ids = [coco.getImgIds(catIds=[id]) for id in cat_ids]
    n_images = len(list(set([item for sublist in img_ids for item in sublist])))

    # get distribution of the categories in the dataset
    cat_dist = dict([(id, len(coco.getImgIds(catIds=[id]))) for id in cat_ids])

    # add the background counts
    class_dist = {0: n_images}
    class_dist.update(cat_dist)

    return class_dist


def get_class_weights(class_dist):
    """
    Compute class weights using the formula n_samples / (n_classes * np.bincount(y))

    Parameters
    ----------
    class_dist: dict
       Distribution of the categories in the dataset

    Returns
    -------
    list
       Array with class_weight_vect[i] the weight for i-th class.
    """

    n_samples = class_dist[0]
    n_classes = len(class_dist)

    return n_samples / (n_classes * np.array(list(class_dist.values())))


def show_im(img_path, img=None):
    """
    Auxiliary function to plot images.

    Parameters
    ----------
    img_path : str
      The file location from which read the image. It is ignored if you pass img.
    img : np.array, optional
      If you have a np.array object in a form of image, you can pass it direcly.
    """

    fig = plt.figsize=(10,)

    # read image from the defined path if img it is available
    if img is None:
        img = mpimg.imread(img_path)

    plt.imshow(img)
    plt.axis('off')
    plt.show()


def show_mask(img, mask, class_names, alpha=0.5, figsize=(5, 5)):
    """
    Auxiliary function to plot images with mask overlapped.

    Parameters
    ----------
    img : np.array
        Image to plot as background
    mask : np.array
        Mask to plot as foreground
    class_names : list
        List of categories containing also the background category.
        Its size must be equal to the number of channels in the mask
    alpha : double, optional
        Transparency of the mask. Default is 0.6
    figsize : pair, optional
        Size of the figure to plot
    """
    plt.figure(figsize=figsize)

    # Preparing the mask with overlapping
    mask_plot = np.zeros((mask.shape[0], mask.shape[1]), dtype=np.float32)
    for i in range(len(class_names)):
        k = i + 1
        mask_plot += mask[:, :, i] * k
        mask_plot[mask_plot >= k] = k
    values = np.array(np.unique(mask_plot), dtype=np.uint8)

    # plot image as background
    plt.imshow(img)

    # plot foreground mask
    im = plt.imshow(mask_plot, interpolation='none', alpha=alpha, cmap='rainbow')

    # add none label
    labels = ['none'] + class_names

    # legend for mask colors
    colors = [im.cmap(im.norm(value)) for value in range(len(labels))]
    patches = [mpatches.Patch(color=colors[i], label=labels[i]) for i in values]
    plt.legend(handles=patches, bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.)

    plt.axis('off')
    plt.show()


def show_multiple_im(input_img_paths, target_img_paths, class_names, predictions=None, figsize=(10, 10)):
    """
    Auxiliary function to plot a batch of images.

    Parameters
    ----------
    input_img_paths : str
        The file locations from which read the input images.
    target_img_paths : str
        The file locations from which read the masks.
    class_names : list
        Array of the categories to show on segmentation masks
    predictions : np.array, optional
        Batch of predictions.
    figsize :  array
        Size of the figure to plot.
    """

    n_images = len(input_img_paths)

    # plot 3 or 2 columns if predictions is available or not
    ncols = 2 if predictions is None else 3

    fig, axes = plt.subplots(figsize=figsize, nrows=n_images, ncols=ncols)

    for i, (input_img_path, target_img_path) in enumerate(zip(input_img_paths, target_img_paths)):
        img = mpimg.imread(input_img_path)
        ax = axes[i, 0] if n_images > 1 else axes[0]
        ax.imshow(img)
        ax.axis('off')

        mask = img_to_array(load_img(target_img_path, color_mode="grayscale"))
        ax = axes[i, 1] if n_images > 1 else axes[1]
        im = ax.imshow(mask[:, :, 0])
        ax.axis('off')

        values = np.array(np.unique(mask), dtype=np.uint8)
        colors = [im.cmap(im.norm(value)) for value in range(len(class_names))]
        patches = [mpatches.Patch(color=colors[i], label=class_names[i]) for i in values]
        ax.legend(handles=patches, bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.)

        if predictions is not None:
            ax = axes[i, 2] if n_images > 1 else axes[2]
            ax.imshow(predictions[i])
            ax.axis('off')

            values = np.array(np.unique(predictions[i]), dtype=np.uint8)
            colors = [im.cmap(im.norm(value)) for value in range(len(class_names))]
            patches = [mpatches.Patch(color=colors[i], label=class_names[i]) for i in values]
            ax.legend(handles=patches, bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.)

    # set column title
    col_titles = ['Input', 'Target', 'Predictions']
    if n_images > 1:
        for ax, col in zip(axes[0], col_titles):
            ax.set_title(col)
    else:
        for ax, col in zip(axes, col_titles):
            ax.set_title(col)

    fig.tight_layout()
    plt.show()


def plot_class_dist(class_dist, cat_names, cat_to_class, without_background=False, figsize=(12, 8)):
    """
    Plot a pie chart of the class distribution

    Parameters
    ----------
    class_dist: dict
       Distribution of the categories in the dataset
    cat_names: list
        Category names ordered and containing the special category 'background'
    cat_to_class: dict
        Map from cat_ids to to the corresponded index of class_names
    without_background: bool, optional
        Decide if the background will be included or not in the plot. Default is False
    figsize:  array
        Size of the figure to plot.
    """

    # sort class_distr
    class_dist_sorted = dict(sorted(class_dist.items(), key=lambda x: x[1], reverse=True))

    if without_background:
        del class_dist_sorted[0]    # not consider background class

    # set data
    labels = [cat_names[cat_to_class[cat_id]] for cat_id in class_dist_sorted.keys()]
    data = list(class_dist_sorted.values())

    # colors
    colors = cm.rainbow(np.linspace(0, 1, len(class_dist_sorted)))

    # explosion
    explode = [0.1] * len(class_dist_sorted)

    # Wedge properties
    wp = {'linewidth': 1, 'edgecolor': "black"}

    # Creating plot
    fig, ax = plt.subplots(figsize=figsize)
    wedges, texts, autotexts = ax.pie(data,
                                      autopct='%1.1f%%',
                                      pctdistance=0.9,
                                      explode=explode,
                                      labels=labels,
                                      shadow=True,
                                      colors=colors,
                                      startangle=90,
                                      wedgeprops=wp
                                      )

    # Adding legend
    ax.legend(wedges, labels,
              title="Categories",
              loc="center left",
              bbox_to_anchor=(1.3, 0, 0.5, 1))

    plt.setp(autotexts, size=8)
    ax.set_title("Distribution of the categories")

    # show plot
    plt.show()