# -*- coding: utf-8 -*-

###############################################################################
#  Copyright Kitware Inc.
#
#  Licensed under the Apache License, Version 2.0 ( the "License" );
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################

import pathlib
import re
from typing import Dict, List
import warnings

import numpy as np
with warnings.catch_warnings():
    # See https://stackoverflow.com/a/40846742
    warnings.filterwarnings(
        'ignore',
        r'^numpy\.dtype size changed, may indicate binary incompatibility\.',
        RuntimeWarning)
    import pandas as pd

from isic_challenge_scoring import metrics  # noqa: E402
from isic_challenge_scoring.scoreCommon import ScoreException  # noqa: E402


CATEGORIES = pd.Index(['MEL', 'NV', 'BCC', 'AKIEC', 'BKL', 'DF', 'VASC'])
EXCLUDE_LABELS = ['ISIC_0035068']


def parseCsv(csvFileStream) -> pd.DataFrame:
    probabilities = pd.read_csv(
        csvFileStream,
        header=0
    )

    if 'image' not in probabilities.columns:
        raise ScoreException('Missing column in CSV: "image".')

    probabilities.set_index('image', drop=True, inplace=True, verify_integrity=True)

    missingColumns = CATEGORIES.difference(probabilities.columns)
    if not missingColumns.empty:
        raise ScoreException(f'Missing columns in CSV: {list(missingColumns)}.')

    extraColumns = probabilities.columns.difference(CATEGORIES)
    if not extraColumns.empty:
        raise ScoreException(f'Extra columns in CSV: {list(extraColumns)}.')

    # sort by the order in CATEGORIES
    probabilities = probabilities.reindex(CATEGORIES, axis='columns')

    missingRows = probabilities[probabilities.isnull().any(axis='columns')].index
    if not missingRows.empty:
        raise ScoreException(f'Missing value(s) in CSV for images: {missingRows.tolist()}.')

    nonFloatColumns = probabilities.dtypes[probabilities.dtypes.apply(
        lambda x: x != np.float64
    )].index
    if not nonFloatColumns.empty:
        raise ScoreException(
            f'CSV contains non-floating-point value(s) in columns: {nonFloatColumns.tolist()}.')
    # TODO: identify specific failed rows

    outOfRangeRows = probabilities[probabilities.applymap(
        lambda x: x < 0.0 or x > 1.0
    ).any(axis='columns')].index
    if not outOfRangeRows.empty:
        raise ScoreException(
            f'Values in CSV are outside the interval [0.0, 1.0] for images: '
            f'{outOfRangeRows.tolist()}.')

    # TODO: fail on extra columns in data rows

    return probabilities


def excludeRows(probabilities: pd.DataFrame, labels: List):
    """Exclude rows with specified labels, in-place."""
    probabilities.drop(index=labels, inplace=True, errors='ignore')


def validateRows(truthProbabilities: pd.DataFrame, predictionProbabilities: pd.DataFrame):
    """
    Ensure prediction rows correspond to truth rows.

    Fail when predictionProbabilities is missing rows or has extra rows compared to
    truthProbabilities.
    """
    missingImages = truthProbabilities.index.difference(predictionProbabilities.index)
    if not missingImages.empty:
        raise ScoreException(f'Missing images in CSV: {missingImages.tolist()}.')

    extraImages = predictionProbabilities.index.difference(truthProbabilities.index)
    if not extraImages.empty:
        raise ScoreException(f'Extra images in CSV: {extraImages.tolist()}.')


def sortRows(probabilities: pd.DataFrame):
    """Sort rows by labels, in-place."""
    probabilities.sort_index(axis='rows', inplace=True)


def computeMetrics(truthFileStream, predictionFileStream) -> List[Dict]:
    truthProbabilities = parseCsv(truthFileStream)
    predictionProbabilities = parseCsv(predictionFileStream)

    excludeRows(truthProbabilities, EXCLUDE_LABELS)
    excludeRows(predictionProbabilities, EXCLUDE_LABELS)

    validateRows(truthProbabilities, predictionProbabilities)

    sortRows(truthProbabilities)
    sortRows(predictionProbabilities)

    scores = [
        {
            'dataset': 'aggregate',
            'metrics': [
                {
                    'name': 'balanced_accuracy',
                    'value': metrics.balancedMulticlassAccuracy(
                        truthProbabilities, predictionProbabilities)
                }
            ]
        },
    ]

    for category in CATEGORIES:
        truthCategoryProbabilities: pd.Series = truthProbabilities[category]
        predictionCategoryProbabilities: pd.Series = predictionProbabilities[category]

        truthBinaryValues: pd.Series = truthCategoryProbabilities.gt(0.5)
        predictionBinaryValues: pd.Series = predictionCategoryProbabilities.gt(0.5)

        scores.append({
            'dataset': category,
            'metrics': [
                {
                    'name': 'accuracy',
                    'value': metrics.binaryAccuracy(truthBinaryValues, predictionBinaryValues)
                },
                {
                    'name': 'sensitivity',
                    'value': metrics.binarySensitivity(truthBinaryValues, predictionBinaryValues)
                },
                {
                    'name': 'specificity',
                    'value': metrics.binarySpecificity(truthBinaryValues, predictionBinaryValues)
                },
                {
                    'name': 'f1_score',
                    'value': metrics.binaryF1(truthBinaryValues, predictionBinaryValues)
                },
                {
                    'name': 'ppv',
                    'value': metrics.binaryPpv(truthBinaryValues, predictionBinaryValues)
                },
                {
                    'name': 'npv',
                    'value': metrics.binaryNpv(truthBinaryValues, predictionBinaryValues)
                },
                {
                    'name': 'auc',
                    'value': metrics.auc(
                        truthCategoryProbabilities, predictionCategoryProbabilities)
                },
                {
                    'name': 'auc_sens_80',
                    'value': metrics.aucAboveSensitivity(
                        truthCategoryProbabilities, predictionCategoryProbabilities, 0.80)
                },
            ]
        })

    return scores


def scoreP3(truthPath: pathlib.Path, predictionPath: pathlib.Path) -> List[Dict]:
    for truthFile in truthPath.iterdir():
        if re.match(r'^ISIC.*GroundTruth\.csv$', truthFile.name):
            break
    else:
        raise ScoreException('Internal error, truth file could not be found.')

    predictionFiles = list(
        predictionFile
        for predictionFile in predictionPath.iterdir()
        if predictionFile.suffix.lower() == '.csv'
    )
    if len(predictionFiles) > 1:
        raise ScoreException(
            'Multiple prediction files submitted. Exactly one CSV file should be submitted.')
    elif len(predictionFiles) < 1:
        raise ScoreException(
            'No prediction files submitted. Exactly one CSV file should be submitted.')
    predictionFile = predictionFiles[0]

    with truthFile.open('rb') as truthFileStream, predictionFile.open('rb') as predictionFileStream:
        return computeMetrics(truthFileStream, predictionFileStream)
