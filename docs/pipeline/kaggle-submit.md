<!-- [Mar 29] Created by SD with GPT-5.4. -->
# Kaggle Submit

Qwen3.5-0.8B 기반 hybrid notebook 제출 절차.

## 1. 필요한 Kaggle Dataset Assets

노트북은 아래 asset 이름을 우선적으로 찾는다.

- base model:
  - `qwen3-5-0-8b`
  - 또는 `qwen35-08b`
- adapter:
  - `qwen35-sft-adapter`
  - 또는 `arc-agi-3-qwen-adapter`

## 2. 업로드할 폴더

### Base model asset

로컬 캐시 경로:

`/Users/sundong/.cache/huggingface/hub/models--Qwen--Qwen3.5-0.8B/snapshots/2fc06364715b967f1860aea9cf38778875588b17`

이 디렉토리 전체를 Kaggle Dataset으로 업로드하고 dataset name을 `qwen3-5-0-8b`로 맞추는 것이 가장 간단하다.

### Adapter asset

학습 결과 디렉토리 예:

- `/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/qwen35_sft_adapter_tiny_mps`
- `/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/qwen35_sft_adapter_stage1_mps`

이 폴더를 Kaggle Dataset으로 업로드하고 dataset name을 `qwen35-sft-adapter`로 맞추면 notebook이 바로 읽는다.

## 3. Notebook 쪽 자산 탐색

[`kaggle_submission.ipynb`](/Users/sundong/Documents/arc-agi-3/kaggle_submission.ipynb)는 아래 경로를 찾는다.

- `/kaggle/input/qwen3-5-0-8b`
- `/kaggle/input/qwen35-08b`
- `/kaggle/input/qwen35-sft-adapter`
- `/kaggle/input/arc-agi-3-qwen-adapter`

## 4. 추천 제출 순서

1. `small_policy_prior.pt` asset 업로드
2. `qwen3-5-0-8b` base model asset 업로드
3. 학습된 adapter asset 업로드
4. notebook에서 세 asset을 모두 attach
5. dry run
6. competition submit

## 5. 첫 제출 추천

첫 제출은 아래 조합이 안전하다.

- CNN online learner
- `small_policy_prior.pt`
- tiny/stage1 Qwen adapter

처음부터 큰 adapter 하나만 믿기보다 fallback이 있는 hybrid로 제출하는 편이 안정적이다.

## 6. 현재 추천 자산

현재 추천 adapter:

- [`qwen35_sft_adapter_stage1b_mps`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/qwen35_sft_adapter_stage1b_mps)

업로드용 폴더 갱신:

```bash
cd /Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents
python scripts/prepare_kaggle_assets.py --adapter-name qwen35_sft_adapter_stage1b_mps
```

생성물:

- [`artifacts/kaggle_upload/qwen35-sft-adapter`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/kaggle_upload/qwen35-sft-adapter)
- [`artifacts/kaggle_upload/small-policy-prior`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/kaggle_upload/small-policy-prior)
- [`artifacts/kaggle_upload/manifest.json`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/kaggle_upload/manifest.json)

## 7. 제출 직전 체크리스트

1. Kaggle dataset `qwen3-5-0-8b` 업로드 또는 attach
2. Kaggle dataset `qwen35-sft-adapter` 업로드 또는 attach
3. `small_policy_prior.pt`를 별도 dataset 또는 같은 asset bundle에 포함
4. [`kaggle_submission.ipynb`](/Users/sundong/Documents/arc-agi-3/kaggle_submission.ipynb) 에 세 asset이 attach 되었는지 확인
5. notebook dry run
6. competition rerun 제출

## 8. Kaggle CLI 예시

kernel bundle 생성:

```bash
cd /Users/sundong/Documents/arc-agi-3
python code/ARC-AGI-3-Agents/scripts/prepare_kaggle_kernel.py
```

생성물:

- [`artifacts/kaggle_kernel_bundle`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/kaggle_kernel_bundle)
- [`kernel-metadata.json`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/kaggle_kernel_bundle/kernel-metadata.json)

adapter dataset 업로드:

```bash
cd /Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/kaggle_upload/qwen35-sft-adapter
kaggle datasets version -p . -m "Update qwen35 stage1b adapter"
```

prior dataset 업로드:

```bash
cd /Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/kaggle_upload/small-policy-prior
kaggle datasets version -p . -m "Update small policy prior"
```

base model dataset 업로드:

```bash
cd /Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/kaggle_upload/qwen3-5-0-8b
kaggle datasets version -p . -m "Update qwen3.5 0.8b base model"
```

notebook push:

```bash
kaggle kernels push -p /Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/kaggle_kernel_bundle
```

notebook status:

```bash
kaggle kernels status sundong/arc-agi-3-hybrid-stage1b
```

competition notebook 제출:

```bash
kaggle competitions submit -c arc-prize-2026-arc-agi-3 \
  -f submission.parquet \
  -k sundong/<NOTEBOOK> \
  -v <VERSION> \
  -m "Message"
```
