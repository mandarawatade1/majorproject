---
title: "Lab Manual: Machine Learning Laboratory, Semester VII"
doc_id: "DEMO/LAB/CE/ML/2026"
is_demo: true
demo_reason: "Internal teaching material for enrolled students, not published.
  Synthesised to provide lab content in the same subject area as the project
  itself, which is a useful adversarial case for retrieval: the vocabulary
  overlaps with the system's own documentation."
category: "lab_manual"
department: "Computer Engineering"
created: "2026-01-06"
---

## Environment

Python with scikit-learn, pandas and matplotlib on the lab workstations.
Datasets are provided locally; do not download datasets from the internet during
lab sessions.

Set a random seed in every experiment and record it. An unreproducible result is
not a result.

## Experiment 1: Data exploration and preparation

Load a provided tabular dataset. Report missing values, distributions and
outliers. Handle missing values and justify the choice.

**Expected observation.** Report what proportion of rows you dropped or imputed.
Dropping 40% of the data to avoid imputation is a decision that must be
defended, not hidden.

## Experiment 2: Train, validation and test splits

Split the data and explain why the test set is touched exactly once.

**Expected observation.** Fit a scaler on the whole dataset before splitting,
then fit it correctly on the training split only. Report both test scores. The
gap between them is leakage, and quantifying it here is the point of the
experiment.

## Experiment 3: Linear and logistic regression

Fit both on appropriate targets. Report the relevant metrics.

**Expected observation.** For the classifier, report accuracy alongside
precision, recall and F1 on an imbalanced target. Explain why accuracy alone is
misleading, using your own numbers.

## Experiment 4: Decision trees and overfitting

Fit an unconstrained tree, then constrain depth and leaf size.

**Expected observation.** Plot training and validation score against depth.
Identify where they diverge. That divergence is overfitting made visible.

## Experiment 5: Ensembles

Fit a random forest and a gradient boosting model.

**Expected observation.** Compare against the single tree. Report feature
importances and state plainly whether they are stable across seeds — they often
are not, and reporting an unstable importance as a finding is a common error.

## Experiment 6: Cross-validation and hyperparameter search

Run k-fold cross-validation and a grid search.

**Expected observation.** Report mean and standard deviation across folds, not
just the mean. A model scoring 0.82 ± 0.01 and one scoring 0.82 ± 0.11 are not
equivalent.

## Experiment 7: Clustering

Apply k-means and hierarchical clustering. Choose k with the elbow and
silhouette methods.

**Expected observation.** The two methods may suggest different k. Report both
and state which you chose and why, rather than reporting only the one that
agreed with your expectation.

## Experiment 8: Text vectorisation and similarity

Vectorise a small document set with TF-IDF and with sentence embeddings.
Retrieve the most similar documents for a query.

**Expected observation.** Find a query where the embedding retrieval succeeds
and TF-IDF fails, and one where the reverse holds. This experiment is the
foundation of hybrid retrieval, and the failure cases matter more than the
successes.

## Submission

Notebook or script, the recorded seed, and the observation section. Results
without a stated seed are not accepted.
