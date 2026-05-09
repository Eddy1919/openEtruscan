# Bibliography

Consolidated reference list for the OpenEtruscan corpus, the Rosetta
vector-space research strand ([`FINDINGS.md`](FINDINGS.md)), and the
corpus-curation cycle ([`CURATION_FINDINGS.md`](CURATION_FINDINGS.md)).
Citations are alphabetized by author within each section.

## Etruscan philology and epigraphy

* **Bonfante, G. & Bonfante, L.** (2002). *The Etruscan Language: An Introduction.* Revised edition. Manchester University Press, Manchester. ISBN 978-0719055409.
  *Standard introductory grammar; the reference for the Latin ↔ Old Italic letter correspondence used to regenerate the `canonical_italic` column. Source for the 62 anchor word-pairs in the Rosetta evaluation harness.*

* **Krummrey, H. & Panciera, S.** (1980). "Criteri di edizione e segni diacritici." *Tituli* 2, pp. 205–215. Edizioni di Storia e Letteratura, Rome.
  *Original codification of the Leiden Convention diacritical signs (`[ ]`, `< >`, `{ }`, `( )`, `?`, `---`) used in the `canonical_transliterated` column. The conventions are still standard in classical epigraphy.*

* **Pallottino, M.** (1968). *Testimonia Linguae Etruscae.* 2nd edition. La Nuova Italia, Florence.
  *Italian-school transliteration tradition (uses σ for the san sibilant). Source for the conventional vocabulary and the inscription-typology categories (funerary / votive / dedicatory / boundary / legal / commercial / ownership) reused in our keyword vocabulary at [`src/openetruscan/ml/classifier.py`](../src/openetruscan/ml/classifier.py).*

* **Rix, H., ed.** (1991). *Etruskische Texte: Editio minor.* Tübingen: Gunter Narr Verlag.
  *Source of the ETP / Pallottino-Rix inscription identifier convention (`Ta 1.81`, `Cr 3.20`, `ETP 339`, etc.) used as the primary key throughout the OpenEtruscan dataset.*

* **van Heesch, J.** (2010). "Roman numerals in epigraphy." In: *Numbers and Numbers*, ed. K. Verboven. Acta Classica Universitatis Scientiarum Debreceniensis 46, pp. 27–44.
  *Reference for Roman numeral character set (I, V, X, L, C, D, M) used in the `has_latin_orthography` abstention rule (Finding 2.1).*

* **Wallace, R. E.** (2008). *Zikh Rasna: A Manual of the Etruscan Language and Inscriptions.* Beech Stave Press, Ann Arbor.
  *Anglo-American transliteration tradition (uses ś for the san sibilant). Authoritative recent reference for Etruscan phonology and morphology. Source for the sibilant-unification rule.*

## Datasets

* **Vico, G. & Spanakis, G.** (2023). "Larth: Dataset and Machine Translation for Etruscan." In: *Proceedings of the Ancient Language Processing Workshop, EMNLP 2023*, pp. 32–42.
  *The 7,139-row Etruscan corpus that seeds OpenEtruscan (~71% of the merged dataset). Source of the `translation` (n=2,891 with English glosses), `Year - From`, and `Year - To` columns merged into [`openetruscan_clean.csv`](data/openetruscan_clean.csv). GitHub: https://github.com/GianlucaVico/Larth-Etruscan-NLP*

* **Pauli, C. et al.**, eds. (1893–). *Corpus Inscriptionum Etruscarum* (CIE), Vols. I–. Barth, Leipzig.
  *Vol. I extractions provide the 1,855 OpenEtruscan inscriptions not present in Larth. The CIE numbering convention (`CIE 2615`, `CIE 261`, etc.) is the second primary identifier scheme in our corpus.*

* **Etruscan Texts Project (ETP).** University of Massachusetts Amherst.
  *Source of inscriptions with `ETP` identifier prefix. Modern digital corpus extending Rix (1991).*

## Machine learning architectures

### Embeddings and contextual representations

* **Conneau, A., Khandelwal, K., Goyal, N., Chaudhary, V., Wenzek, G., Guzmán, F., Grave, E., Ott, M., Zettlemoyer, L. & Stoyanov, V.** (2020). "Unsupervised Cross-lingual Representation Learning at Scale." In: *Proceedings of ACL 2020*, pp. 8440–8451. arXiv:1911.02116.
  *XLM-RoBERTa, the encoder used in the `etr-lora-v3` and `etr-lora-v4` Etruscan embedders.*

* **Feng, F., Yang, Y., Cer, D., Arivazhagan, N. & Wang, W.** (2022). "Language-Agnostic BERT Sentence Embedding." In: *ACL 2022 Findings*, pp. 878–891.
  *LaBSE; the multilingual sentence-embedding model used in the Rosetta vector-space strand (see [`FINDINGS.md`](FINDINGS.md)).*

* **Hu, E. J., Shen, Y., Wallis, P., Allen-Zhu, Z., Li, Y., Wang, S., Wang, L. & Chen, W.** (2022). "LoRA: Low-Rank Adaptation of Large Language Models." In: *ICLR 2022*. arXiv:2106.09685.
  *The parameter-efficient fine-tuning method used for both `etr-lora` (XLM-R) and the failed ByT5 v4/v5 experiments. Finding 6.2 documents the limits of LoRA r=8 on byte-level + sentinel-token convergence.*

### Sequence-to-sequence and span corruption

* **Raffel, C., Shazeer, N., Roberts, A., Lee, K., Narang, S., Matena, M., Zhou, Y., Li, W. & Liu, P. J.** (2020). "Exploring the Limits of Transfer Learning with a Unified Text-to-Text Transformer." *Journal of Machine Learning Research* 21(140):1–67.
  *T5 / span-corruption objective. The `<extra_id_0>` ... `<extra_id_99>` sentinel mechanism used in our ByT5 lacuna experiments comes from this paper.*

* **Xue, L., Barua, A., Constant, N., Al-Rfou, R., Narang, S., Kale, M., Roberts, A. & Raffel, C.** (2022). "ByT5: Towards a Token-Free Future with Pre-trained Byte-to-Byte Models." *Transactions of the Association for Computational Linguistics* 10:291–306. arXiv:2105.13626.
  *The byte-level T5 variant we used for the v3 / v4 / v5 lacuna restoration adapters. Finding 6.2 documents why byte-level + sentinel + LoRA r=8 doesn't converge on ~6k samples.*

### Loss functions and class imbalance

* **Lin, T.-Y., Goyal, P., Girshick, R., He, K. & Dollár, P.** (2017). "Focal Loss for Dense Object Detection." In: *ICCV 2017*, pp. 2980–2988. arXiv:1708.02002.
  *α-balanced focal loss, used in the MicroTransformer + CharCNN classifier training to handle the extreme class imbalance (funerary 57%, commercial 0.3%) in the cascade-labeled training set.*

### Computer vision (glyph detection)

* **Jocher, G., Chaurasia, A. & Qiu, J.** (2024). "YOLO11 by Ultralytics." Ultralytics, GitHub: https://github.com/ultralytics/ultralytics.
  *YOLO11n architecture used for the Etruscan glyph detector at `runs/detect/runs/glyph_detector/`. The model is described in [`src/cv_pipeline/train_yolo.py`](../src/cv_pipeline/train_yolo.py).*

## Methodological and statistical references

* **Bagnall, R. S. & Cribiore, R.** (2006). *Women's Letters from Ancient Egypt, 300 BC – AD 800.* University of Michigan Press, Ann Arbor.
  *Modern reference summarizing the Leiden Convention (Krummrey & Panciera 1980) for non-classicist readers. Useful as a teaching reference for new contributors.*

* **Efron, B. & Tibshirani, R. J.** (1993). *An Introduction to the Bootstrap.* Chapman & Hall, New York.
  *Source of the bootstrap confidence-interval methodology referenced in Finding 8.2 for held-out F1 estimates at small n.*

## Software and tooling

* **Anthropic.** (2026). *Claude Code* (CLI agent for software engineering, accessed May 2026).
  *Used as the primary reasoning agent for the held-out labeling (Finding 8.1), the cascade labeler design ([`scripts/data_pipeline/claude_label_corpus.py`](../scripts/data_pipeline/claude_label_corpus.py)), and the auditing of the failed ByT5 experiment (Finding 6.2).*

* **HuggingFace Transformers** (Wolf et al. 2020). *Transformers: State-of-the-Art Natural Language Processing.* In: *EMNLP 2020 System Demonstrations*. arXiv:1910.03771.
  *Library used for all transformer model loading, training, and inference in this work.*

* **HuggingFace PEFT** (Mangrulkar et al. 2022). *PEFT: State-of-the-art Parameter-Efficient Fine-Tuning.* GitHub: https://github.com/huggingface/peft.
  *The LoRA adapter implementation used in the etr-lora and ByT5 experiments.*

* **Pinecone Pgvector / Pgvector contributors.** (2024). *pgvector: Open-source vector similarity search for Postgres.* GitHub: https://github.com/pgvector/pgvector.
  *PostgreSQL extension powering the production semantic-search HNSW indexes built on the etr-lora-v3 / v4 768-dimensional embeddings.*

## Conventions and style

* **ISO 639-3.** (2007). *Codes for the representation of names of languages — Part 3: Alpha-3 code for comprehensive coverage of languages.* International Organization for Standardization, Geneva.
  *Source of the language code `ett` (Etruscan) used in the dataset metadata and Zenodo deposit.*

* **Unicode Consortium.** (2023). *The Unicode Standard, Version 15.1.* Unicode, Inc., Mountain View.
  *Reference for the Old Italic block U+10300–U+1032F, the Greek block U+0370–U+03FF, and the diacritical / mirror-glyph code points enumerated in [`scripts/data_pipeline/normalize_inscriptions.py`](../scripts/data_pipeline/normalize_inscriptions.py).*
