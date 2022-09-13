import sys
import os
import pickle
import subprocess

from pandas.api import types as pd_types
import numpy as np

from mindsdb.integrations.libs.const import PREDICTOR_STATUS


class BYOMHandler:

    name = 'byom'

    def __init__(self, handler_storage, model_storage):
        self.handler_storage = handler_storage
        self.model_storage = model_storage

    def _run_command(self, params):
        params_enc = pickle.dumps(params)

        # TODO change to virtualenv from config
        python_path = sys.executable
        wrapper_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'proc_wrapper.py')
        p = subprocess.Popen(
            [python_path, wrapper_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        p.stdin.write(params_enc)
        p.stdin.close()
        p.wait()

        ret_enc = p.stdout.read()
        try:
            ret = pickle.loads(ret_enc)
        except (pickle.UnpicklingError, EOFError):
            raise RuntimeError(p.stderr.read())
        return ret

    def create_connection(self, connection_args):
        model_code = connection_args['model_code']
        self.handler_storage.file_set('model_code', model_code)

    def _get_model_code(self):
        # TODO :
        # return self.handler_storage.file_get('model_code')

        # temporal solution
        return self.handler_storage.get_connection_args()['model_code']

    def learn(self, training_data_df, to_predict):
        params = {
            'method': 'train',
            'df': training_data_df,
            'code': self._get_model_code(),
            'to_predict': to_predict
        }
        try:
            model_params = self._run_command(params)
            encoded = pickle.dumps(model_params)
            self.model_storage.file_set('model', encoded)

            # TODO return columns?

            def convert_type(field_type):
                if pd_types.is_integer_dtype(field_type):
                    return 'integer'
                elif pd_types.is_numeric_dtype(field_type):
                    return 'float'
                elif pd_types.is_datetime64_any_dtype(field_type):
                    return 'datetime'
                else:
                    return 'categorical'

            columns = {
                to_predict: convert_type(np.object)
            }

            self.model_storage.columns_set(columns)

            self.model_storage.status_set(PREDICTOR_STATUS.COMPLETE)

        except Exception as e:
            status_info = {"error": str(e)}
            self.model_storage.status_set(PREDICTOR_STATUS.ERROR, status_info=status_info)

    def predict(self, df):
        encoded = self.model_storage.file_get('model')
        model_params = pickle.loads(encoded)
        params = {
            'method': 'predict',
            'code': self._get_model_code(),
            'df': df,
            'model': model_params,
        }
        pred_df = self._run_command(params)

        # rename target column
        target = self.model_storage.get_info()['to_predict'][0]
        pred_df = pred_df.rename(columns={target: 'prediction'})
        return pred_df


    def describe(self):
        # TODO should it be ml-handler depended?
        pass