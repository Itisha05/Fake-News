import torch
from transformers import AutoTokenizer, BertForSequenceClassification
import os
import json

model_path = os.path.join(r"C:\Users\Trishla\Desktop\IBM Project\Fake News Detection\fake_news_bert_model\fake_news_bert_model")
tokenizer = AutoTokenizer.from_pretrained(model_path)
model = BertForSequenceClassification.from_pretrained(model_path)
model.eval()

texts = [
    "5G causes coronavirus.",
    "5G Towers Linked to Rapid Spread of COVID-19 in Urban Areas.",
    "Recent reports circulating online claim that 5G mobile towers are responsible for accelerating the spread of COVID-19 in major cities. According to several unverified sources, radiation emitted from these towers weakens the human immune system, making individuals more vulnerable to viral infections. Authorities have denied these claims, but many citizens remain concerned about the potential health risks associated with 5G technology.",
    "asdlkfj qwerlkj asdfzxczv",
    "Hello",
]

output_data = []

with torch.no_grad():
    for i, t in enumerate(texts):
        # Scenario 1: Pad to MAX_LEN
        enc_max = tokenizer(t, max_length=256, padding='max_length', truncation=True, return_tensors='pt')
        out_max = model(**enc_max).logits[0]
        probs_max = torch.softmax(out_max, dim=0).numpy()
        
        output_data.append({
            "id": i+1,
            "text": t[:30] + "...",
            "tokens": len(tokenizer.tokenize(t)),
            "logit_0": float(out_max[0]),
            "logit_1": float(out_max[1]),
            "prob_fake": float(probs_max[0]*100),
            "prob_real": float(probs_max[1]*100)
        })

with open("deep_output.json", "w") as f:
    json.dump(output_data, f, indent=4)

print("Done writing deep_output.json")
