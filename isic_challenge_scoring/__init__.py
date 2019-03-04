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

import json
import os
import pathlib
import shutil
import tempfile
from typing import Tuple
import zipfile

from .scoreCommon import ScoreException
from .task1 import score as scoreTask1
from .task2 import score as scoreTask2
from .task3 import scoreP3


def extractZip(zipPath: pathlib.Path, outputPath: pathlib.Path, flatten: bool = True):
    """
    Extract a zip file, optionally flattening it into a single directory.
    """
    try:
        with zipfile.ZipFile(zipPath) as zf:
            if flatten:
                for memberInfo in zf.infolist():
                    memberName = memberInfo.filename
                    if memberName.startswith('__MACOSX'):
                        # Ignore Mac OS X metadata
                        continue

                    memberBaseName = os.path.basename(memberName)
                    if not memberBaseName:
                        # Skip directories
                        continue

                    memberOutputPath = outputPath / memberBaseName

                    with zf.open(memberInfo) as inputStream, \
                            memberOutputPath.open('wb') as outputStream:
                        shutil.copyfileobj(inputStream, outputStream)
            else:
                zf.extractall(outputPath)
    except zipfile.BadZipfile as e:
        raise ScoreException(f'Could not read ZIP file "{zipPath.name}": {str(e)}.')


def unzipAll(inputPath: pathlib.Path, allowManuscriptDirectory: bool = False) -> \
        Tuple[pathlib.Path, tempfile.TemporaryDirectory]:
    """
    Extract / copy all files in directory. Validate that the path contains
    exactly one file. Optionally allow an 'Abstract' directory to exist that
    contains exactly one manuscript file.
    Return a path to the extracted content.
    """
    inputFiles = [f for f in inputPath.iterdir() if f.is_file()]
    inputDirs = [f for f in inputPath.iterdir() if f.is_dir()]

    if len(inputFiles) > 1:
        raise ScoreException(
            'Multiple files submitted. Exactly one ZIP file should be submitted.')
    elif len(inputFiles) < 1:
        raise ScoreException(
            'No files submitted. Exactly one ZIP file should be submitted.')

    inputFile = inputFiles[0]

    manuscriptFile = None

    if allowManuscriptDirectory:
        if len(inputDirs) > 1:
            raise ScoreException('Internal error: multiple directories found.')
        elif len(inputDirs) == 1:
            inputDir = inputDirs[0]
            if inputDir.name != 'Abstract':
                raise ScoreException(
                    f'Internal error: unexpected directory found: {inputDir.name}.')

            manuscriptFiles = list(inputDir.iterdir())
            if not manuscriptFiles:
                raise ScoreException('Empty manuscript directory found.')
            elif len(manuscriptFiles) > 1:
                raise ScoreException('Multiple files found in manuscript directory.')

            manuscriptFile = manuscriptFiles[0]
    elif inputDirs:
        # Expect only files
        raise ScoreException('Internal error: unexpected directory found.')

    outputTempDir = tempfile.TemporaryDirectory()
    outputPath = pathlib.Path(outputTempDir.name)

    if inputFile.suffix.lower() == '.zip':
        extractZip(inputFile, outputPath)
    else:
        shutil.copy(inputFile, outputPath)

    if manuscriptFile is not None:
        shutil.copy(manuscriptFile, outputPath)

    return outputPath, outputTempDir


def ensureManuscript(predictionPath: pathlib.Path):
    manuscriptFileCount = sum(
        manuscriptFile.suffix.lower() == '.pdf'
        for manuscriptFile in predictionPath.iterdir()
    )
    if manuscriptFileCount > 1:
        raise ScoreException(
            'Multiple PDFs submitted. Exactly one PDF file, containing the descriptive manuscript, '
            'must included in the submission.')
    elif manuscriptFileCount < 1:
        raise ScoreException(
            'No PDF submitted. Exactly one PDF file, containing the descriptive manuscript, '
            'must included in the submission.')


def scoreAll(truthInputPath: pathlib.Path, predictionInputPath: pathlib.Path,
             taskNum: int, requireManuscript: bool):
    # Unzip zip files contained in the input folders
    truthPath, truthTempDir = unzipAll(truthInputPath)

    predictionPath, predictionTempDir = unzipAll(predictionInputPath, allowManuscriptDirectory=True)

    if requireManuscript:
        ensureManuscript(predictionPath)

    if taskNum == 1:
        scores = scoreTask1(truthPath, predictionPath)
    elif taskNum == 2:
        scores = scoreTask2(truthPath, predictionPath)
    elif taskNum == 3:
        scores = scoreP3(truthPath, predictionPath)
    else:
        raise ScoreException(
            f'Internal error: unknown ground truth phase number: {taskNum}.')

    print(json.dumps(scores))

    truthTempDir.cleanup()
    predictionTempDir.cleanup()
