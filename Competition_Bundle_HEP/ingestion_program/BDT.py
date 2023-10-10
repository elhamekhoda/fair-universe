import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier


EPSILON = np.finfo(float).eps


# ------------------------------
# Two layerd Neural Network
# ------------------------------
# class TwoLayerNN(nn.Module):

#     def __init__(self, input_size, hidden_size1, hidden_size2, output_size):
#         super(TwoLayerNN, self).__init__()
#         self.fc1 = nn.Linear(input_size, hidden_size1)
#         self.relu1 = nn.ReLU()
#         self.fc2 = nn.Linear(hidden_size1, hidden_size2)
#         self.relu2 = nn.ReLU()
#         self.fc3 = nn.Linear(hidden_size2, output_size)

#     def forward(self, x):
#         out = self.fc1(x)
#         out = self.relu1(out)
#         out = self.fc2(out)
#         out = self.relu2(out)
#         out = self.fc3(out)
#         out = torch.sigmoid(out)
#         return out


# ------------------------------
# Custom Dataset
# ------------------------------
# class CustomDataset(Dataset):
#     def __init__(self, data, labels=None):
#         self.data = data
#         self.labels = labels

#     def __len__(self):
#         return len(self.data)

#     def __getitem__(self, idx):
#         sample = {'data': self.data[idx]}
#         if self.labels is not None:
#             sample['labels'] = self.labels[idx]
#         return sample


# ------------------------------
# Baseline Model
# ------------------------------
class Model():
    """
    This is a model class to be submitted by the participants in their submission.

    This class should consists of the following functions
    1) init : initialize a classifier
    2) fit : can be used to train a classifier
    3) predict: predict mu_hat and delta_mu_hat

    Note:   Add more methods if needed e.g. save model, load pre-trained model etc.
            It is the participant's responsibility to make sure that the submission 
            class is named "Model" and that its constructor arguments remains the same.
            The ingestion program initializes the Model class and calls fit and predict methods
    """

    def __init__(
            self,
            train_set=None,
            test_sets=[],
            test_sets_weights=[],
            systematics=None,
            model_name="BDT",
            
    ):
        """
        Model class constructor

        Params:
            train_set:
                labelled train set

            test_sets:
                unlabelled test sets

            systematics:
                systematics class

            model_name:
                name of the model, default: NN

        Returns:
            None
        """

        # Set class variables from parameters

        self.model_name = model_name
        self.train_set = train_set
        self.test_sets = []
        self.test_sets_weights = []
        for test_set in test_sets:
            self.test_sets.append({"data": test_set})

        for test_set_weights in test_sets_weights:
            self.test_sets_weights.append(test_set_weights) 

        self.systematics = systematics

        # Intialize class variables
        self.validation_sets = None
        self.theta_candidates = np.arange(0, 1, 0.1)
        self.best_theta = None

        # Hyper params
        self.num_epochs = 10
        self.batch_size = 32

    def fit(self):
        """
        Params:
            None

        Functionality:
            this function can be used to train a model using the train set

        Returns:
            None
        """

        self._generate_validation_sets()
        self._init_model()
        self._train()
        self._choose_theta()
        self._validate()
        self._compute_validation_result()

    def predict(self):
        """
        Params:
            None

        Functionality:
           to predict using the test sets

        Returns:
            dict with keys
                - mu_hat
                - delta_mu_hat
        """

        self._test()
        self._compute_test_result()

        return {
            "mu_hats": self.mu_hats,
            "delta_mu_hat": self.delta_mu_hat
        }

    def _init_model(self):
        print("[*] - Intialize BDT")

        self.model = XGBClassifier(tree_method="hist",use_label_encoder=False,eval_metric='logloss')


    def _generate_validation_sets(self):
        print("[*] - Generating Validation sets")

        # Calculate the sum of weights for signal and background in the original dataset
        signal_weights = self.train_set["weights"][self.train_set["labels"] == 1].sum()
        background_weights = self.train_set["weights"][self.train_set["labels"] == 0].sum()

        # Split the data into training and validation sets while preserving the proportion of samples with respect to the target variable
        train_df, valid_df, train_label, valid_label, train_weights, valid_weights = train_test_split(
            self.train_set["data"],
            self.train_set["labels"],
            self.train_set["weights"],
            test_size=0.3,
            stratify=self.train_set["labels"]
        )

        # Calculate the sum of weights for signal and background in the training and validation sets
        train_signal_weights = train_weights[train_label == 1].sum()
        train_background_weights = train_weights[train_label == 0].sum()
        valid_signal_weights = valid_weights[valid_label == 1].sum()
        valid_background_weights = valid_weights[valid_label == 0].sum()

        # Balance the sum of weights for signal and background in the training and validation sets
        train_weights[train_label == 1] *= signal_weights / train_signal_weights
        train_weights[train_label == 0] *= background_weights / train_background_weights
        valid_weights[valid_label == 1] *= signal_weights / valid_signal_weights
        valid_weights[valid_label == 0] *= background_weights / valid_background_weights

        self.train_set = {
            "data": train_df,
            "labels": train_label,
            "weights": train_weights,
            "settings": self.train_set["settings"]
        }

        self.validation_sets = []
        # Loop 10 times to generate 10 validation sets
        for i in range(0, 10):
            tes = round(np.random.uniform(0.9, 1.10), 2)
            # apply systematics
            valid_with_systematics = self.systematics(
                data=valid_df,
                tes=tes
            ).data
            self.validation_sets.append({
                "data": valid_with_systematics,
                "labels": valid_label,
                "weights": valid_weights,
                "settings": self.train_set["settings"]
            })

    def _train(self):
        print("[*] - Train Neural Network")

        self._init_model()

        weights_train = self.train_set["weights"].copy()

            
                
        class_weights_train = (weights_train[self.train_set['labels'] == 0].sum(), weights_train[self.train_set['labels'] == 1].sum())

        for i in range(len(class_weights_train)): # loop on B then S target
            #training dataset: equalize number of background and signal
            weights_train[self.train_set['labels'] == i] *= max(class_weights_train)/ class_weights_train[i] 
            #test dataset : increase test weight to compensate for sampling


        print("[*] --- Training Model")
        self._fit(self.train_set['data'], self.train_set['labels'], weights_train)

        print("[*] --- Predicting Train set")
        self.train_set['predictions'] = self._predict(self.train_set['data'], 0.95)

    def _fit(self, X, y,w):
        self.model.fit(X, y,sample_weight = w) 
    

    def _predict(self, X, theta):
        y_predict = self.model.predict_proba(X)[:,1]
        predictions = np.where(y_predict > theta, 1, 0) 
        return predictions


    def get_meta_validation_set(self):

        meta_validation_data = []
        meta_validation_labels = []
        meta_validation_weights = []

        for valid_set in self.validation_sets:
            meta_validation_data.append(valid_set['data'])
            meta_validation_labels = np.concatenate((meta_validation_labels, valid_set['labels']))
            meta_validation_weights = np.concatenate((meta_validation_weights, valid_set['weights']))

        return {
            'data': pd.concat(meta_validation_data),
            'labels': meta_validation_labels,
            'weights': meta_validation_weights
        }

    def _choose_theta(self):

        print("[*] Choose best theta")

        meta_validation_set = self.get_meta_validation_set()
        theta_sigma_squared = []

        # Loop over theta candidates
        # try each theta on meta-validation set
        # choose best theta
        for theta in self.theta_candidates:

            # Get predictions from trained model
            Y_hat_valid = self._predict(meta_validation_set['data'], theta)
            Y_valid = meta_validation_set["labels"]

            # print("sum of signal" , meta_validation_set["weights"][Y_hat_valid == 1].sum())
            # print("sum of background" , meta_validation_set["weights"][Y_hat_valid == 0].sum()) 

            # get region of interest
            roi_indexes = np.argwhere(Y_hat_valid == 1)
            roi_points = Y_valid[roi_indexes]
            # compute nu_roi
            nu_roi = meta_validation_set["weights"][roi_indexes].sum()/10

            # compute gamma_roi
            indexes = np.argwhere(roi_points == 0)
            print(roi_points)
            print(len(indexes))

            # get signal class predictions
            signal_predictions = roi_points[indexes]

            gamma_roi = meta_validation_set["weights"][indexes].sum()/10

            # compute beta_roi
            bkg_indexes = np.argwhere(roi_points == 0)
            beta_roi = meta_validation_set["weights"][bkg_indexes].sum()/10

            # print(nu_roi, gamma_roi, nu_roi/np.square(gamma_roi))
            print(f"\n[*] --- nu_roi: {nu_roi} --- beta_roi: {beta_roi} --- gamma_roi: {gamma_roi}")


            # Compute sigma squared mu hat
            sigma_squared_mu_hat = nu_roi/np.square(gamma_roi)

            # get N_ROI from predictions
            theta_sigma_squared.append(sigma_squared_mu_hat)

        # Choose theta with min sigma squared
        try:
            index_of_least_sigma_squared = np.nanargmin(theta_sigma_squared)
        except:
            print("[!] - WARNING! All sigma squared are nan")
            index_of_least_sigma_squared = np.argmin(theta_sigma_squared)

        # self.best_theta = self.theta_candidates[index_of_least_sigma_squared]
        self.best_theta = 0.95

        print(f"[*] --- Best theta : {self.best_theta}")

    def _validate(self):
        for valid_set in self.validation_sets:
            valid_set['predictions'] = self._predict(valid_set['data'], self.best_theta)

    def _compute_validation_result(self):

        print("[*] - Computing Validation result")

        delta_mu_hats = []
        for valid_set in self.validation_sets:

            Y_hat_train = self.train_set["predictions"]
            Y_train = self.train_set["labels"]
            Y_hat_valid = valid_set["predictions"]

            Y_index = np.argwhere(Y_hat_valid == 1)
            n_roi = valid_set["weights"][Y_index].sum()

            # get region of interest
            roi_indexes = np.argwhere(Y_hat_train == 1)
            roi_points = Y_train[roi_indexes]

            # compute nu_roi
            nu_roi = self.train_set["weights"][roi_indexes].sum()

            # compute gamma_roi
            indexes = np.argwhere(roi_points == 1)

            # get signal class predictions
            signal_predictions = roi_points[indexes]
            gamma_roi = self.train_set["weights"][indexes].sum()

            # compute beta_roi
            bkg_indexes = np.argwhere(roi_points == 0)
            beta_roi = self.train_set["weights"][bkg_indexes].sum()

            if gamma_roi == 0:
                gamma_roi = EPSILON

            # Compute mu_hat
            mu_hat = (n_roi - beta_roi)/gamma_roi

            # Compute delta mu hat (absolute value)
            delta_mu_hat = np.abs(valid_set["settings"]["ground_truth_mu"] - mu_hat)

            delta_mu_hats.append(delta_mu_hat)

            print(f"[*] --- n_roi : {n_roi} --- nu_roi: {nu_roi} --- beta_roi: {beta_roi} --- gamma_roi: {gamma_roi}")
            print(f"[*] --- mu: {np.round(valid_set['settings']['ground_truth_mu'], 2)} --- mu_hat: {np.round(mu_hat, 2)} --- delta_mu_hat: {np.round(delta_mu_hat, 2)}")

        # Average delta mu_hat
        self.delta_mu_hat = np.mean(delta_mu_hats)
        print(f"[*] --- delta_mu_hat (avg): {np.round(self.delta_mu_hat, 2)}")

    def _test(self):
        print("[*] - Testing")
        # Get predictions from trained model
        for test_set in self.test_sets:
            test_set['predictions'] = self._predict(test_set['data'], self.best_theta)
        for test_set, test_set_weights in zip(self.test_sets, self.test_sets_weights):
            test_set['weights'] = test_set_weights


    def _compute_test_result(self):

        print("[*] - Computing Test result")

        mu_hats = []
        for test_set in self.test_sets:

            Y_hat_train = self.train_set["predictions"]
            Y_train = self.train_set["labels"]
            Y_hat_test = test_set["predictions"]

            n_roi = test_set["weights"][Y_hat_test == 1].sum()


            # get region of interest
            roi_indexes = np.argwhere(Y_hat_train == 1)
            roi_points = Y_train[roi_indexes]
            # compute nu_roi


            nu_roi = self.train_set["weights"][roi_indexes].sum()

            # compute gamma_roi
            indexes = np.argwhere(roi_points == 1)

            # get signal class predictions
            signal_predictions = roi_points[indexes]
            gamma_roi = self.train_set["weights"][indexes].sum()


            # compute beta_roi
            bkg_indexes = np.argwhere(roi_points == 0)
            beta_roi = self.train_set["weights"][bkg_indexes].sum()

            if gamma_roi == 0:
                gamma_roi = EPSILON

            # Compute mu_hat
            mu_hat = (n_roi - beta_roi)/gamma_roi

            mu_hats.append(mu_hat)
            print(f"[*] --- mu_hat: {np.round(mu_hat, 2)}")

        # Save mu_hat from test
        self.mu_hats = mu_hats
