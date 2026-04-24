import torch
from transformers import AutoTokenizer, BertForSequenceClassification
import os

model_path = os.path.join(r"C:\Users\Trishla\Desktop\IBM Project\Fake News Detection\fake_news_bert_model\fake_news_bert_model")
tokenizer = AutoTokenizer.from_pretrained(model_path)
model = BertForSequenceClassification.from_pretrained(model_path)
model.eval()

texts = [
    # Very short
    "5G causes coronavirus.",
    # Medium
    "5G Towers Linked to Rapid Spread of COVID-19 in Urban Areas.",
    # Long fake
    "Recent reports circulating online claim that 5G mobile towers are responsible for accelerating the spread of COVID-19 in major cities. According to several unverified sources, radiation emitted from these towers weakens the human immune system, making individuals more vulnerable to viral infections. Authorities have denied these claims, but many citizens remain concerned about the potential health risks associated with 5G technology.",
    # Random characters
    "asdlkfj qwerlkj asdfzxczv",
    # Single word
    "Hello",
]

print("=== DEEP MODEL ANALYSIS ===")
with torch.no_grad():
    for i, t in enumerate(texts):
        # Print token length
        tokens = tokenizer.tokenize(t)
        print(f"\n[{i+1}] TEXT: {t[:50]}... (Tokens: {len(tokens)})")
        
        # Scenario 1: Pad to MAX_LEN (What app.py does)
        enc_max = tokenizer(t, max_length=256, padding='max_length', truncation=True, return_tensors='pt')
        out_max = model(**enc_max).logits[0]
        probs_max = torch.softmax(out_max, dim=0).numpy()
        
        # Scenario 2: Dynamic Padding (No forced max length)
        enc_dyn = tokenizer(t, padding=True, truncation=True, return_tensors='pt')
        out_dyn = model(**enc_dyn).logits[0]
        probs_dyn = torch.softmax(out_dyn, dim=0).numpy()
        
        print(f"  -> Logits (Padded to 256): Fake(0)={out_max[0]:.4f}, Real(1)={out_max[1]:.4f}")
        print(f"  -> Probs  (Padded to 256): Fake={probs_max[0]*100:.2f}%, Real={probs_max[1]*100:.2f}%")
        
        if not torch.allclose(out_max, out_dyn, atol=1e-3):
            print(f"  -> WARNING: Dynamic padding changes logits! Fake={out_dyn[0]:.4f}, Real={out_dyn[1]:.4f}")
        else:
            print("  -> Padding length has no effect on model features (Expected).")

print("\n--- Summary of Model Configuration ---")
print(f"Model Labels: {model.config.id2label}")
print(f"Classifier Dropout: {model.config.classifier_dropout}")
