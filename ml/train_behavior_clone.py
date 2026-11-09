"""Starter behavior-cloning trainer for already-aligned frame/action examples.
Expected CSV columns: image_path, action_id. This is a baseline, not a complete FPS policy.
"""
import csv, argparse
from pathlib import Path
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from PIL import Image

class Samples(Dataset):
    def __init__(self, csv_path):
        self.rows=list(csv.DictReader(open(csv_path, newline="", encoding="utf-8")))
        self.tf=transforms.Compose([transforms.Resize((180,320)),transforms.ToTensor()])
    def __len__(self): return len(self.rows)
    def __getitem__(self,i):
        r=self.rows[i]
        return self.tf(Image.open(r["image_path"]).convert("RGB")), int(r["action_id"])

class Policy(nn.Module):
    def __init__(self,n):
        super().__init__()
        self.net=nn.Sequential(nn.Conv2d(3,16,5,2,2),nn.ReLU(),nn.MaxPool2d(2),
          nn.Conv2d(16,32,3,2,1),nn.ReLU(),nn.AdaptiveAvgPool2d((5,8)),
          nn.Flatten(),nn.Linear(32*5*8,256),nn.ReLU(),nn.Linear(256,n))
    def forward(self,x): return self.net(x)

p=argparse.ArgumentParser()
p.add_argument("--csv",required=True); p.add_argument("--classes",type=int,default=8)
p.add_argument("--epochs",type=int,default=10); p.add_argument("--out",default="policy.pt")
a=p.parse_args()
ds=Samples(a.csv); dl=DataLoader(ds,batch_size=32,shuffle=True)
device="cuda" if torch.cuda.is_available() else "cpu"
m=Policy(a.classes).to(device); opt=torch.optim.Adam(m.parameters(),lr=1e-3); loss_fn=nn.CrossEntropyLoss()
for epoch in range(a.epochs):
    m.train(); total=0
    for x,y in dl:
        x,y=x.to(device),y.to(device); opt.zero_grad(); loss=loss_fn(m(x),y); loss.backward(); opt.step(); total+=loss.item()
    print(f"epoch {epoch+1}: loss={total/max(1,len(dl)):.4f}")
torch.save({"state_dict":m.cpu().state_dict(),"classes":a.classes},a.out)
print("Saved baseline policy:",a.out)
