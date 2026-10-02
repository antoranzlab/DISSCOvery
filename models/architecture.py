"""Small complete segmentation networks; no pretrained weights."""
import torch
from torch import nn

class SimpleUNet(nn.Module):
    """Same topology and widths as the saved STS model; independent initialization."""
    def __init__(self):
        super().__init__();self.c1=nn.Conv2d(1,64,3,padding=1);self.c2=nn.Conv2d(64,128,3,padding=1);self.c3=nn.Conv2d(128,256,3,padding=1);self.c4=nn.Conv2d(384,128,3,padding=1);self.c5=nn.Conv2d(192,64,3,padding=1);self.out=nn.Conv2d(64,1,1)
        for m in self.modules():
            if isinstance(m,nn.Conv2d):nn.init.xavier_uniform_(m.weight);nn.init.zeros_(m.bias)
    def forward(self,x):
        a=torch.relu(self.c1(x));b=torch.relu(self.c2(nn.functional.max_pool2d(a,2)));c=torch.relu(self.c3(nn.functional.max_pool2d(b,2)))
        c=torch.relu(self.c4(torch.cat([nn.functional.interpolate(c,scale_factor=2,mode='nearest'),b],1)))
        c=torch.relu(self.c5(torch.cat([nn.functional.interpolate(c,scale_factor=2,mode='nearest'),a],1)))
        return self.out(c)

class Separable(nn.Module):
    def __init__(self,cin,cout):
        super().__init__();self.net=nn.Sequential(nn.Conv2d(cin,cin,3,padding=1,groups=cin),nn.Conv2d(cin,cout,1),nn.ReLU())
    def forward(self,x):return self.net(x)

class SeparableUNet(nn.Module):
    """Same widths/resolutions/skips; each 3x3 becomes depthwise then pointwise."""
    def __init__(self):
        super().__init__();self.c1=Separable(1,64);self.c2=Separable(64,128);self.c3=Separable(128,256);self.c4=Separable(384,128);self.c5=Separable(192,64);self.out=nn.Conv2d(64,1,1)
        for m in self.modules():
            if isinstance(m,nn.Conv2d):nn.init.xavier_uniform_(m.weight);nn.init.zeros_(m.bias)
    def forward(self,x):
        a=self.c1(x);b=self.c2(nn.functional.max_pool2d(a,2));c=self.c3(nn.functional.max_pool2d(b,2))
        c=self.c4(torch.cat([nn.functional.interpolate(c,scale_factor=2,mode='nearest'),b],1))
        c=self.c5(torch.cat([nn.functional.interpolate(c,scale_factor=2,mode='nearest'),a],1));return self.out(c)

class MobileUNet(nn.Module):
    """Real timm MobileNetV4-Conv-Small 0.35 encoder + small custom skip decoder."""
    def __init__(self):
        super().__init__();import timm
        self.encoder=timm.create_model('mobilenetv4_conv_small_035',pretrained=False,in_chans=1,features_only=True)
        ch=self.encoder.feature_info.channels();self.project=nn.Conv2d(ch[-1],64,1)
        self.decode=nn.ModuleList([Separable(cin+skip,cout) for cin,skip,cout in zip([64,64,48,32],ch[-2::-1],[64,48,32,16])]);self.final=Separable(17,16);self.out=nn.Conv2d(16,1,1)
    def forward(self,x):
        feats=self.encoder(x);y=self.project(feats[-1])
        for layer,skip in zip(self.decode,feats[-2::-1]):
            y=layer(torch.cat([nn.functional.interpolate(y,size=skip.shape[-2:],mode='bilinear',align_corners=False),skip],1))
        y=nn.functional.interpolate(y,size=x.shape[-2:],mode='bilinear',align_corners=False)
        return self.out(self.final(torch.cat([y,x],1)))

def build_model(name):
    return {'simple':SimpleUNet,'separable':SeparableUNet,'mobilev4_035':MobileUNet,'existing_STS_topology_random_initialization':SimpleUNet}[name]()
