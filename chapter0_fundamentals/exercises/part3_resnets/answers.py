# %%

import os; os.environ["ACCELERATE_DISABLE_RICH"] = "1"
import sys
import torch as t
from torch import Tensor
from torch import nn
import torch.nn.functional as F
from collections import OrderedDict
from einops import rearrange
from dataclasses import dataclass
from torchvision import datasets, transforms, models
from torch.utils.data import DataLoader, Subset
from tqdm.notebook import tqdm
from typing import List, Tuple, Dict
from PIL import Image
from IPython.display import display
from pathlib import Path
import torchinfo
import json
import pandas as pd
from jaxtyping import Float, Int
import pytorch_lightning as pl
from pytorch_lightning.loggers import CSVLogger

# Make sure exercises are in the path
chapter = r"chapter0_fundamentals"
exercises_dir = Path(f"{os.getcwd().split(chapter)[0]}/{chapter}/exercises").resolve()
section_dir = exercises_dir / "part3_resnets"
if str(exercises_dir) not in sys.path: sys.path.append(str(exercises_dir))
os.chdir(section_dir)

from part2_cnns.solutions import get_mnist, Linear, Conv2d, Flatten, ReLU, MaxPool2d
from part3_resnets.utils import print_param_count
import part3_resnets.tests as tests
from plotly_utils import line, plot_train_loss_and_test_accuracy_from_metrics

device = t.device('cuda' if t.cuda.is_available() else 'cpu')

MAIN = __name__ == "__main__"

# %%
if MAIN:
    device = t.device('cuda' if t.cuda.is_available() else 'cpu')

    # Assuming that we are on a CUDA machine, this should print a CUDA device:
    print(device)

# %%

class ConvNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = Conv2d(1, 32, kernel_size=3, padding=1)
        self.relu1 = ReLU()
        self.max1 = MaxPool2d(2, stride=2, padding=0)
        self.conv2 = Conv2d(32,64, kernel_size=3, padding=1, stride=1)
        self.relu2 = ReLU()
        self.max2 = MaxPool2d(2, stride=2, padding=0)
        self.flatten = Flatten()
        self.linear1 = Linear(3136, 128)
        self.relu3 = ReLU()
        self.linear2 = Linear(128,10)


    def forward(self, x: t.Tensor) -> t.Tensor:
        x = self.conv1(x)
        x = self.relu1(x)
        x = self.max1(x)
        x = self.conv2(x)
        x = self.relu2(x)
        x = self.max2(x)
        x = self.flatten(x)
        x = self.linear1(x)
        x = self.relu3(x)
        x = self.linear2(x)
        return x

if MAIN:
    model = ConvNet()
    print(model)

# %%

if MAIN:
    summary = torchinfo.summary(model, input_size=(1, 1, 28, 28))
    print(summary)

# %%

if MAIN:
    MNIST_TRANSFORM = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])

def get_mnist(subset: int = 1):
    '''Returns MNIST training data, sampled by the frequency given in `subset`.'''
    mnist_trainset = datasets.MNIST(root="./data", train=True, download=True, transform=MNIST_TRANSFORM)
    mnist_testset = datasets.MNIST(root="./data", train=False, download=True, transform=MNIST_TRANSFORM)

    if subset > 1:
        mnist_trainset = Subset(mnist_trainset, indices=range(0, len(mnist_trainset), subset))
        mnist_testset = Subset(mnist_testset, indices=range(0, len(mnist_testset), subset))

    return mnist_trainset, mnist_testset



if MAIN:
    mnist_trainset, mnist_testset = get_mnist()
    mnist_trainloader = DataLoader(mnist_trainset, batch_size=64, shuffle=True)
    mnist_testloader = DataLoader(mnist_testset, batch_size=64, shuffle=False)

# %%
if MAIN:
    model = ConvNet().to(device)

    batch_size = 64
    epochs = 3

    mnist_trainset, _ = get_mnist(subset = 10)
    mnist_trainloader = DataLoader(mnist_trainset, batch_size=64, shuffle=True)

    optimizer = t.optim.Adam(model.parameters())
    loss_list = []

    for epoch in tqdm(range(epochs)):
        for imgs, labels in mnist_trainloader:
            imgs = imgs.to(device)
            labels = labels.to(device)
            logits = model(imgs)
            loss = F.cross_entropy(logits, labels)
            loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            loss_list.append(loss.item())   # .item() converts single-elem tensor to scalar

# %%
if MAIN:
    line(
        loss_list, 
        yaxis_range=[0, max(loss_list) + 0.1],
        labels={"x": "Num batches seen", "y": "Cross entropy loss"}, 
        title="ConvNet training on MNIST",
        width=700
    )
# %%
import pytorch_lightning as pl
from pytorch_lightning.loggers import CSVLogger

# %%
class LitConvNet(pl.LightningModule):
    def __init__(self):
        super().__init__()
        self.convnet = ConvNet()

    def training_step(self, batch: Tuple[t.Tensor, t.Tensor], batch_idx: int) -> t.Tensor:
        '''
        Here you compute and return the training loss and some additional metrics for e.g. the progress bar or logger.
        '''
        imgs, labels = batch
        logits = self.convnet(imgs)
        loss = F.cross_entropy(logits, labels)
        self.log("train_loss", loss)
        return loss

    def configure_optimizers(self):
        '''
        Choose what optimizers and learning-rate schedulers to use in your optimization.
        '''
        optimizer = t.optim.Adam(self.parameters())
        return optimizer
    
# %%

# Set batch size

if MAIN:
    batch_size = 64
    max_epochs = 3

    # Create the model & training system
    model = LitConvNet()

    # Get dataloaders
    trainset, testset = get_mnist(subset = 10)
    trainloader = DataLoader(trainset, shuffle=True, batch_size=batch_size)
    testloader = DataLoader(testset, shuffle=True, batch_size=batch_size)

    # Get a logger, to record metrics during training
    logger = CSVLogger(save_dir=os.getcwd() + "/logs", name="day4-convenet")

    # Train the model (hint: here are some helpful Trainer arguments for rapid idea iteration)
    trainer = pl.Trainer(
        max_epochs=max_epochs,
        logger=logger,
        log_every_n_steps=1,
    )
    trainer.fit(model=model, train_dataloaders=trainloader)

# %%
if MAIN:
    metrics = pd.read_csv(f"{trainer.logger.log_dir}/metrics.csv")

    metrics.head()

# %%

if MAIN:
    line(
        metrics["train_loss"].values,
        x=metrics["step"].values,
        yaxis_range=[0, metrics["train_loss"].max() + 0.1],
        labels={"x": "Batches seen", "y": "Cross entropy loss"},
        title="ConvNet training on MNIST",
        width=800,
        hovermode="x unified",
        template="ggplot2", # alternative aesthetic for your plots (-:
    )
# %%
@dataclass
class ConvNetTrainingArgs():
    '''
    Defining this class implicitly creates an __init__ method, which sets arguments as 
    given below, e.g. self.batch_size = 64. Any of these arguments can also be overridden
    when you create an instance, e.g. args = ConvNetTrainingArgs(batch_size=128).
    '''
    batch_size: int = 64
    max_epochs: int = 3
    optimizer: t.optim.Optimizer = t.optim.Adam
    learning_rate: float = 1e-3
    log_dir: str = os.getcwd() + "/logs"
    log_name: str = "day4-convenet"
    log_every_n_steps: int = 1
    sample: int = 10

    def __post_init__(self):
        '''
        This code runs after the class is instantiated. It can reference things like
        self.sample, which are defined in the __init__ block.
        '''
        trainset, testset = get_mnist(subset=self.sample)
        self.trainloader = DataLoader(trainset, shuffle=True, batch_size=self.batch_size)
        self.testloader = DataLoader(testset, shuffle=False, batch_size=self.batch_size)
        self.logger = CSVLogger(save_dir=self.log_dir, name=self.log_name)


class LitConvNet(pl.LightningModule):
    def __init__(self, args: ConvNetTrainingArgs):
        super().__init__()
        self.convnet = ConvNet()
        self.args = args

    def training_step(self, batch: Tuple[t.Tensor, t.Tensor], batch_idx: int) -> t.Tensor:
        imgs, labels = batch
        logits = self.convnet(imgs)
        loss = F.cross_entropy(logits, labels)
        self.log("train_loss", loss)

        return loss
    
    def validation_step(self, batch: Tuple[t.Tensor, t.Tensor], batch_idx: int) -> t.Tensor:
        imgs, labels = batch
        logits = self.convnet(imgs)
        acc = t.mean((labels == t.argmax(logits, dim=-1)), dtype=t.float16)
        self.log("accuracy", acc)

    def configure_optimizers(self):
        optimizer = self.args.optimizer(self.parameters(), lr=self.args.learning_rate)
        return optimizer



if MAIN:
    args = ConvNetTrainingArgs()
    model = LitConvNet(args)

    trainer = pl.Trainer(
        max_epochs=args.max_epochs,
        logger=args.logger,
        log_every_n_steps=1
    )
    trainer.fit(model=model, train_dataloaders=args.trainloader, val_dataloaders=args.testloader)

# %%
if MAIN:
    metrics = pd.read_csv(f"{trainer.logger.log_dir}/metrics.csv")
    plot_train_loss_and_test_accuracy_from_metrics(metrics, "Training ConvNet on MNIST data")