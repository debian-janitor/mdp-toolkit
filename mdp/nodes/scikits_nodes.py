"""Wraps the algorithms defined in scikits.learn in MDP Nodes.

This module is based on the 0.6.X branch of scikits.learn .
"""
import scikits.learn
import inspect

import mdp

class ScikitsException(mdp.NodeException):
    """Base class for exceptions in nodes wrapping scikits algorithms."""
    pass

# import all submodules of scikits.learn (to work around lazy import)
scikits_modules = ['ann', 'cluster', 'covariance', 'feature_extraction',
                   'feature_selection', 'features', 'gaussian_process', 'glm',
                   'linear_model', 'preprocessing', 'svm',
                   'pca', 'lda', 'hmm', 'fastica', 'grid_search', 'mixture',
                   'naive_bayes', 'neighbors', 'qda']
for name in scikits_modules:
    # not all modules may be available due to missing dependencies
    # on the user system.
    # we just ignore failing imports
    try:
        __import__('scikits.learn.' + name)
    except ImportError:
        pass

# TODO: generalize dtype support
# TODO: have a look at predict_proba for Classifier.prob
# TODO: inverse <-> generate/rvs
# TODO: deal with input_dim/output_dim
# TODO: change signature of overwritten functions
# TODO: wrap_scikits_instance
# TODO: add scikits.learn availability to test info strings
# TODO: which tests ? (test that particular algorithm are / are not trainable)
# XXX: if class defines n_components, allow output_dim, otherwise throw exception
#      also for classifiers (overwrite _set_output_dim)

def apply_to_scikits_algorithms(current_module, action,
                                processed_modules=None,
                                processed_classes=None):
    """ Function that traverses a module to find scikits algorithms.
    
    'scikits.learn' algorithms are identified by the 'fit' 'predict',
    or 'transform' methods. The 'action' function is applied to each found
    algorithm.
    
    action -- a function that is called with as action(class_), where
              class_ is a class that defines the 'fit' or 'predict' method
    """

    # only consider modules and classes once
    if processed_modules is None:
        processed_modules = []
    if processed_classes is None:
        processed_classes = []

    if current_module in processed_modules:
        return
    processed_modules.append(current_module)

    for member_name, member in current_module.__dict__.items():
        if not member_name.startswith('_'):

            # classes
            if (inspect.isclass(member) and
                member not in processed_classes):
                processed_classes.append(member)
                if ((hasattr(member, 'fit')
                     or hasattr(member, 'predict')
                     or hasattr(member, 'transform'))
                    and not member.__module__.endswith('_')):
                    action(member)

            # other modules
            elif (inspect.ismodule(member)
                  and member.__name__.startswith('scikits.learn')):
                apply_to_scikits_algorithms(member, action, processed_modules,
                                            processed_classes)
    return processed_classes


_DOC_TEMPLATE = """
[This node has been automatically generated by wrapping the
%s.%s class from the scikits.learn library.
The wrapped instance can be accessed through the 'scikits_alg' attribute.]

%s
"""

_OUTPUTDIM_ERROR = """'output_dim' keyword not supported.
                
Please set the output dimensionality using scikits.learn keyword
arguments (e.g., 'n_components', or 'k'). See the docstring of this
class for details."""

def wrap_scikits_classifier(scikits_class):
    """Wrap a scikits.learn classifier as an MDP Node subclass.

    The wrapper maps these MDP methods to their scikits.learn equivalents:
    _stop_training -> fit
    _label -> predict
    """

    newaxis = mdp.numx.newaxis

    # create a wrapper class for a scikits.learn classifier
    class ScikitsNode(mdp.ClassifierCumulator):

        def __init__(self, input_dim=None, output_dim=None, dtype=None,
                     **kwargs):
            if output_dim is not None:
                raise ScikitsException(_OUTPUTDIM_ERROR)
            super(ScikitsNode, self).__init__(input_dim=input_dim,
                                              output_dim=output_dim,
                                              dtype=dtype)
            self.scikits_alg = scikits_class(**kwargs)

        # ---- re-direct training and execution to the wrapped algorithm

        def _stop_training(self, **kwargs):
            super(ScikitsNode, self)._stop_training(self)
            return self.scikits_alg.fit(self.data, self.labels, **kwargs)

        def _label(self, x):
            return self.scikits_alg.predict(x)[:, newaxis]

        # ---- administrative details

        @staticmethod
        def is_invertible():
            return False

        @staticmethod
        def is_trainable():
            """Return True if the node can be trained, False otherwise."""
            return hasattr(scikits_class, 'fit')

        # NOTE: at this point scikits nodes can only support up to
        # 64-bits floats because some call numpy.linalg.svd, which for
        # some reason does not support higher precisions
        def _get_supported_dtypes(self):
            """Return the list of dtypes supported by this node.
            The types can be specified in any format allowed by numpy.dtype."""
            return ['float32', 'float64']

    # modify class name and docstring
    ScikitsNode.__name__ = scikits_class.__name__ + 'ScikitsLearnNode'
    ScikitsNode.__doc__ = _DOC_TEMPLATE % (scikits_class.__module__,
                                           scikits_class.__name__,
                                           scikits_class.__doc__)

    # change the docstring of the methods to match the ones in scikits.learn

    # methods_dict maps ScikitsNode method names to scikits.learn method names
    methods_dict = {'__init__': '__init__',
                    'stop_training': 'fit',
                    'label': 'predict'}
    if hasattr(scikits_class, 'predict_proba'):
        methods_dict['prob'] = 'predict_proba'

    for mdp_name, scikits_name in methods_dict.items():
        mdp_method = getattr(ScikitsNode, mdp_name)
        scikits_method = getattr(scikits_class, scikits_name)
        if hasattr(scikits_method, 'im_func'):
            # some scikits algorithms do not define an __init__ method
            # the one inherited from 'object' is a
            # "<slot wrapper '__init__' of 'object' objects>"
            # which does not have a 'im_func' attribute
            mdp_method.im_func.__doc__ = _DOC_TEMPLATE % (scikits_class.__module__,
                                                    scikits_class.__name__,
                                                    scikits_method.im_func.__doc__)

    if scikits_class.__init__.__doc__ is None:
        ScikitsNode.__init__.im_func.__doc__ = _DOC_TEMPLATE % (scikits_class.__module__,
                                                scikits_class.__name__,
                                                scikits_class.__doc__)

    return ScikitsNode


def wrap_scikits_transformer(scikits_class):
    """Wrap a scikits.learn transformer as an MDP Node subclass.

    The wrapper maps these MDP methods to their scikits.learn equivalents:
    _stop_training -> fit
    _execute -> transform
    """

    # create a wrapper class for a scikits.learn transformer
    class ScikitsNode(mdp.Cumulator):

        def __init__(self, input_dim=None, output_dim=None, dtype=None, **kwargs):
            if output_dim is not None:
                raise ScikitsException(_OUTPUTDIM_ERROR)
            super(ScikitsNode, self).__init__(input_dim=input_dim,
                                              output_dim=output_dim,
                                              dtype=dtype)
            self.scikits_alg = scikits_class(**kwargs)

        # ---- re-direct training and execution to the wrapped algorithm

        def _stop_training(self, **kwargs):
            super(ScikitsNode, self)._stop_training(self)
            return self.scikits_alg.fit(self.data, **kwargs)

        def _execute(self, x):
            return self.scikits_alg.transform(x)

        # ---- administrative details

        @staticmethod
        def is_invertible():
            return False

        @staticmethod
        def is_trainable():
            """Return True if the node can be trained, False otherwise."""
            return hasattr(scikits_class, 'fit')

        # NOTE: at this point scikits nodes can only support up to
        # 64-bits floats because some call numpy.linalg.svd, which for
        # some reason does not support higher precisions
        def _get_supported_dtypes(self):
            """Return the list of dtypes supported by this node.
            The types can be specified in any format allowed by numpy.dtype."""
            return ['float32', 'float64']

    # modify class name and docstring
    ScikitsNode.__name__ = scikits_class.__name__ + 'ScikitsLearnNode'
    ScikitsNode.__doc__ = _DOC_TEMPLATE % (scikits_class.__module__,
                                           scikits_class.__name__,
                                           scikits_class.__doc__)

    # change the docstring of the methods to match the ones in scikits.learn

    # methods_dict maps ScikitsNode method names to scikits.learn method names
    methods_dict = {'__init__': '__init__',
                    'stop_training': 'fit',
                    'execute': 'transform'}

    for mdp_name, scikits_name in methods_dict.items():
        mdp_method = getattr(ScikitsNode, mdp_name)
        scikits_method = getattr(scikits_class, scikits_name)
        if hasattr(scikits_method, 'im_func'):
            # some scikits algorithms do not define an __init__ method
            # the one inherited from 'object' is a
            # "<slot wrapper '__init__' of 'object' objects>"
            # which does not have a 'im_func' attribute
            mdp_method.im_func.__doc__ = _DOC_TEMPLATE % (scikits_class.__module__,
                                                    scikits_class.__name__,
                                                    scikits_method.im_func.__doc__)

    if scikits_class.__init__.__doc__ is None:
        ScikitsNode.__init__.im_func.__doc__ = _DOC_TEMPLATE % (scikits_class.__module__,
                                                scikits_class.__name__,
                                                scikits_class.__doc__)
    return ScikitsNode


def wrap_scikits_predictor(scikits_class):
    """Wrap a scikits.learn transformer as an MDP Node subclass.

    The wrapper maps these MDP methods to their scikits.learn equivalents:
    _stop_training -> fit
    _execute -> predict
    """

    # create a wrapper class for a scikits.learn predictor
    class ScikitsNode(mdp.Cumulator):

        def __init__(self, input_dim=None, output_dim=None, dtype=None, **kwargs):
            if output_dim is not None:
                raise ScikitsException(_OUTPUTDIM_ERROR)
            super(ScikitsNode, self).__init__(input_dim=input_dim,
                                              output_dim=output_dim,
                                              dtype=dtype)
            self.scikits_alg = scikits_class(**kwargs)

        # ---- re-direct training and execution to the wrapped algorithm

        def _stop_training(self, **kwargs):
            super(ScikitsNode, self)._stop_training(self)
            return self.scikits_alg.fit(self.data, **kwargs)

        def _execute(self, x):
            return self.scikits_alg.predict(x)

        # ---- administrative details

        @staticmethod
        def is_invertible():
            return False

        @staticmethod
        def is_trainable():
            """Return True if the node can be trained, False otherwise."""
            return hasattr(scikits_class, 'fit')

        # NOTE: at this point scikits nodes can only support up to 64-bits floats
        # because some call numpy.linalg.svd, which for some reason does not
        # support higher precisions
        def _get_supported_dtypes(self):
            """Return the list of dtypes supported by this node.
            The types can be specified in any format allowed by numpy.dtype."""
            return ['float32', 'float64']

    # modify class name and docstring
    ScikitsNode.__name__ = scikits_class.__name__ + 'ScikitsLearnNode'
    ScikitsNode.__doc__ = _DOC_TEMPLATE % (scikits_class.__module__,
                                           scikits_class.__name__,
                                           scikits_class.__doc__)

    # change the docstring of the methods to match the ones in scikits.learn

    # methods_dict maps ScikitsNode method names to scikits.learn method names
    methods_dict = {'__init__': '__init__',
                    'stop_training': 'fit',
                    'execute': 'predict'}

    for mdp_name, scikits_name in methods_dict.items():
        mdp_method = getattr(ScikitsNode, mdp_name)
        scikits_method = getattr(scikits_class, scikits_name)
        if hasattr(scikits_method, 'im_func'):
            # some scikits algorithms do not define an __init__ method
            # the one inherited from 'object' is a
            # "<slot wrapper '__init__' of 'object' objects>"
            # which does not have a 'im_func' attribute
            mdp_method.im_func.__doc__ = _DOC_TEMPLATE % (scikits_class.__module__,
                                                    scikits_class.__name__,
                                                    scikits_method.im_func.__doc__)

    if scikits_class.__init__.__doc__ is None:
        ScikitsNode.__init__.im_func.__doc__ = _DOC_TEMPLATE % (scikits_class.__module__,
                                                scikits_class.__name__,
                                                scikits_class.__doc__)
    return ScikitsNode


#list candidate nodes
def print_public_members(class_):
    """Print methods of scikits.learn algorithm.
    """
    print '\n', '-' * 15
    print '%s (%s)' % (class_.__name__, class_.__module__)
    for attr_name in dir(class_):
        attr = getattr(class_, attr_name)
        #print attr_name, type(attr)
        if not attr_name.startswith('_') and inspect.ismethod(attr):
            print ' -', attr_name

#apply_to_scikits_algorithms(scikits.learn, print_public_members)


def wrap_scikits_algorithms(scikits_class, nodes_list):
    """NEED DOCSTRING."""

    name = scikits_class.__name__
    if (name[:4] == 'Base' or name == 'LinearModel'):
        return

    if issubclass(scikits_class, scikits.learn.base.ClassifierMixin):
        nodes_list.append(wrap_scikits_classifier(scikits_class))
    elif hasattr(scikits_class, 'transform'):
        nodes_list.append(wrap_scikits_transformer(scikits_class))
    elif hasattr(scikits_class, 'predict'):
        nodes_list.append(wrap_scikits_predictor(scikits_class))

scikits_nodes = []
apply_to_scikits_algorithms(scikits.learn,
                            lambda c: wrap_scikits_algorithms(c, scikits_nodes))

# add scikit nodes to dictionary
#scikits_module = new.module('scikits')
DICT_ = {}
for wrapped_c in scikits_nodes:
    #print wrapped_c.__name__
    DICT_[wrapped_c.__name__] = wrapped_c

