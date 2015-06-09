from copy import deepcopy
from facefit import util
from facefit.base import Regressor, RegressorBuilder
from facefit.util import *

class CascadedShapeRegressorBuilder(RegressorBuilder):
    def __init__(self, n_stages, n_perturbations, weak_builder):
        self.n_stages = n_stages
        self.weak_builder = weak_builder
        self.n_perturbations = n_perturbations
        self.n_landmarks = 0

    def build(self, images, gt_shapes, boxes):
        self.mean_shape = util.centered_mean_shape(gt_shapes)
        self.n_landmarks = self.mean_shape.n_points
        # Generate initial shapes with perturbations.
        print_dynamic('Generating initial shapes')
        shapes = np.array([util.fit_shape_to_box(self.mean_shape, box) for box in boxes])

        print_dynamic('Perturbing initial estimates')
        boxes = boxes.repeat(self.n_perturbations, axis=0)
        images = images.repeat(self.n_perturbations, axis=0)
        gt_shapes = gt_shapes.repeat(self.n_perturbations, axis=0)
        shapes = shapes.repeat(self.n_perturbations, axis=0)

        if self.n_perturbations > 1:
            shapes = util.perturb_shapes(shapes, gt_shapes, boxes, self.n_perturbations)

        assert(len(boxes) == len(images))
        assert(len(shapes) == len(images))
        assert(len(gt_shapes) == len(images))

        print('\nSize of augmented dataset: {} images.\n'.format(len(images)))


        weak_regressors = []
        for j in xrange(self.n_stages):
            # Calculate normalized targets.
            deltas = [gt_shapes[i].points - shapes[i].points for i in xrange(len(images))]
            targets = np.array([util.transform_to_mean_shape(shapes[i], self.mean_shape).apply(deltas[i]).reshape((2*self.n_landmarks,))
                                for i in xrange(len(images))])

            weak_regressor = self.weak_builder.build(images, targets, (shapes, self.mean_shape, j))
            # Update current estimates of shapes.
            for i in xrange(len(images)):
                offset = weak_regressor.apply(images[i], shapes[i])
                shapes[i].points += offset.points
            weak_regressors.append(weak_regressor)
            print("\nBuilt outer regressor {}\n".format(j))

        return CascadedShapeRegressor(self.n_landmarks, weak_regressors, self.mean_shape)


class CascadedShapeRegressor:
    def __init__(self, n_landmarks, weak_regressors, mean_shape):
        self.n_landmarks = n_landmarks
        self.weak_regressors = weak_regressors
        self.mean_shape = mean_shape

    def apply(self, image, boxes):
        initial_shapes = np.array([fit_shape_to_box(self.mean_shape, box) for box in boxes])

        shapes = deepcopy(initial_shapes)

        for shape in shapes:
            for r in self.weak_regressors:
                offset = r.apply(image, shape)
                shape.points += offset.points
        return initial_shapes, shapes