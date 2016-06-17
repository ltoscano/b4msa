# author: Eric S. Tellez <eric.tellez@infotec.mx>
# under the same terms than the multilingual benchmark

import numpy as np
import logging
from time import time
from sklearn.metrics import f1_score, accuracy_score
from sklearn import preprocessing
from sklearn import cross_validation

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(x, **kwargs):
        return x

logging.basicConfig(format='%(asctime)s : %(levelname)s :%(message)s')

OPTION_NONE = 'none'
OPTION_GROUP = 'group'
OPTION_DELETE = 'delete'


BASIC_OPTIONS = [OPTION_DELETE, OPTION_GROUP, OPTION_NONE]

_BASE_PARAMS = dict(
    strip_diac=[False, True],
    num_option=BASIC_OPTIONS,
    usr_option=BASIC_OPTIONS,
    url_option=BASIC_OPTIONS,
    lc=[False, True],
    del_dup1=[False, True],
    token_list=[-2, -1, 1, 2, 3, 4, 5, 6, 7],
)

_BASE_PARAMS_LANG = dict(
    strip_diac=[False, True],
    num_option=BASIC_OPTIONS,
    usr_option=BASIC_OPTIONS,
    url_option=BASIC_OPTIONS,
    lc=[False, True],
    del_dup1=[False, True],
    token_list=[-2, -1, 1, 2, 3, 4, 5, 6, 7],
    negation=[False, True],
    stemming=[False, True],
    stopwords=BASIC_OPTIONS
)

BASE_PARAMS = sorted(_BASE_PARAMS.items())
BASE_PARAMS_LANG = sorted(_BASE_PARAMS_LANG.items())


class ParameterSelection:
    def __init__(self):
        pass

    def sample_param_space(self, n, q=3):
        for i in range(n):
            kwargs = {}
            for k, v in self.base_params:
                if len(v) == 0:
                    continue

                if k == 'token_list':
                    x = list(v)
                    np.random.shuffle(x)
                    # qs = np.random.randint(q, len(x))
                    qs = int(round(min(len(x), max(1, np.random.normal(q)))))
                    kwargs[k] = sorted(x[:qs])
                else:
                    kwargs[k] = v[np.random.randint(len(v))]

            yield kwargs

    def expand_neighbors(self, s):
        for k, v in sorted(s.items()):
            if k[0] == '_':
                # by convention, metadata starts with underscore
                continue
            
            if v in (True, False):
                x = s.copy()
                x[k] = not v
                yield x
            elif v in BASIC_OPTIONS:
                for _v in BASIC_OPTIONS:
                    if _v != v:
                        x = s.copy()
                        x[k] = _v
                        yield x
            elif k == 'token_list':
                for i in range(len(v)):
                    x = s.copy()
                    l = x[k] = x[k].copy()
                    l.pop(i)
                    yield x

                for _v in self._base_params[k]:
                    if _v not in v:
                        x = s.copy()
                        l = x[k] = x[k].copy()
                        l.append(_v)
                        l.sort()
                        yield x

    def search(self, fun_score, bsize=32, qsize=3,
               hill_climbing=True, lang=None, pool=None):
        if lang:
            self.base_params = BASE_PARAMS_LANG
            self._base_params = _BASE_PARAMS_LANG
        else:
            self.base_params = BASE_PARAMS
            self._base_params = _BASE_PARAMS
            
        tabu = set()  # memory for tabu search

        # initial approximation, montecarlo based process
        def get_best(cand, desc="searching for params"):
            if pool is None:
                # X = list(map(fun_score, cand))
                X = [fun_score(x) for x in tqdm(cand, desc=desc, total=len(cand))]
            else:
                # X = list(pool.map(fun_score, cand))
                X = [x for x in tqdm(pool.imap_unordered(fun_score, cand), desc=desc, total=len(cand))]

            # a list of tuples (score, conf)
            X.sort(key=lambda x: x['_score'], reverse=True)
            return X

        L = []
        for conf in self.sample_param_space(bsize, q=qsize):
            code = get_filename(conf)
            if code in tabu:
                continue

            tabu.add(code)
            L.append((conf, code))
            
        best_list = get_best(L)
        if hill_climbing:
            # second approximation, hill climbing process
            i = 0
            while True:
                i += 1
                bscore = best_list[0]['_score']
                L = []

                for conf in self.expand_neighbors(best_list[0]):
                    code = get_filename(conf)
                    if code in tabu:
                        continue

                    tabu.add(code)
                    L.append((conf, code))

                best_list.extend(get_best(L, desc="hill climbing iteration {0}".format(i)))
                best_list.sort(key=lambda x: x['_score'], reverse=True)
                if bscore == best_list[0]['_score']:
                    break

        return best_list


class Wrapper(object):
    def __init__(self, X, y, n_folds, cls, seed=0, pool=None):
        self.n_folds = n_folds
        self.X = X
        le = preprocessing.LabelEncoder().fit(y)
        self.y = np.array(le.transform(y))
        self.cls = cls
        self.pool = pool
        np.random.seed(seed)
        self.kfolds = [x for x in cross_validation.StratifiedKFold(y,
                                                                   n_folds=n_folds,
                                                                   shuffle=True,
                                                                   random_state=seed)]

    def f(self, conf_code):
        conf, code = conf_code
        st = time()
        hy = self.cls.predict_kfold(self.X, self.y, self.n_folds,
                                    textModel_params=conf,
                                    kfolds=self.kfolds,
                                    pool=self.pool,
                                    use_tqdm=False)

        conf['_macro_f1'] = f1_score(self.y, hy, average='macro')
        conf['_weighted_f1'] = f1_score(self.y, hy, average='weighted')
        conf['_accuracy'] = accuracy_score(self.y, hy)
        conf['_score'] = conf['_macro_f1']
        
        conf['_time'] = (time() - st) / self.n_folds
        return conf

                
def get_filename(kwargs, basename=None):
    L = []
    if basename:
        L.append(basename)
        
    for k, v in sorted(kwargs.items()):
        L.append("{0}={1}".format(k, v).replace(" ", ""))

    return "-".join(L)
