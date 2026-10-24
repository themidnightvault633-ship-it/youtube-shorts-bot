import base64
import logging
import lzma
import math
from pathlib import Path
import numpy as np

# ================= PILLOW ANTIALIAS COMPATIBILITY PATCH =================
import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = getattr(PIL.Image, "LANCZOS", PIL.Image.BICUBIC)
if not hasattr(PIL.Image, "LANCZOS"):
    PIL.Image.LANCZOS = PIL.Image.BICUBIC
# ========================================================================

from PIL import Image, ImageDraw, ImageFont

# Universal MoviePy 1.x & 2.x Import Layer
try:
    from moviepy.editor import (
        ImageClip, VideoClip, VideoFileClip, AudioFileClip,
        concatenate_videoclips, clips_array, ColorClip,
        CompositeVideoClip, concatenate_audioclips, vfx
    )
except ImportError:
    from moviepy import (
        ImageClip, VideoClip, VideoFileClip, AudioFileClip,
        concatenate_videoclips, clips_array, ColorClip,
        CompositeVideoClip, concatenate_audioclips, vfx
    )

from config import (
    SHORT_WIDTH, SHORT_HEIGHT, LONG_WIDTH, LONG_HEIGHT,
    FPS, ASSETS_DIR
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

RESAMPLE_FILTER = getattr(Image, "LANCZOS", Image.BICUBIC)

# Built-in LZMA+Base85 compressed studio anchor video clip (from 1000121747.mp4)
# Ensures the bottom half NEVER goes black even if anchor_studio.mp4 is not uploaded to GitHub.
EMBEDDED_ANCHOR_B85 = (
"{Wp48S^xk9=GL@E0stWa8~^|S5YJf5;8$%^hFt&vXa;Pj5XX=V2;Ut1t?rX)G!YS0cwqFYlMs-|OO=#KUuFtjUwQZVP|wHugw|^H!!_LjaM@mfGWBwA8e_H2"
"1jYxk*H}q}qvNEW6`R~AlEY0|+;;gwG<K%$J~)WH2tm*bdyKZhN{z+1GjRn<|5cQJWl6kdC-&D5Pa`0@cCMOv`_M}3Ha~-LL@EUccTl0o{HjPvM!9z-m2a)$"
"G)LH8h;r5!qJoa4quZ8V@Z93l0d6J2v-|mkFi4c{1?_D;ZQqz6-%hGrG2Iu8pMi})<Tp{5${>sReeEIkf0R2v3L|-8XD19o>rx((?j|)n)rFolUb@*?ZKmmD"
"PD7^-6-;V$&sPg3DAoxMgelW=)(Uaa13l|apyRJNdGQW@C?jY=lXKq{zDkChQ`|@s`dH>v{dC%xl$zjP2Pir*!?(5#Z}TDhvFoRYg6PTTddkT4`Ze*wF1&h@"
"C}ClEH&>TlujOXPq?@Y0{zg@W5M2iPESx8zK4#8`*niW?l{F`{TcaON=f(mq@*AQ4gbi1$MWy`5??E$xL18!QJIHD&17xo+OqBcV@Q`aPAmYPZ5nCgM2ml1*"
"gGejlW7GGtA{$O0Dt^=9?<1CT_jI&^<z+lJjkpXOAn1nLPp9WHWic1wfMO>`bLxl*+D>eeU>$Nql?C&~_S1)#4J|l>BItENjynL6IL6e(1jN<R^r^1a*_B{&"
"an)%&O|=(lT!H!oo+K5Y&ig<UY}y~D03=c=^=3p<eJqale2=VU_3CV{O&{Hu?$R*EZPgtS>p$ZYXIaqAeDDmJ7w;h8`kHtyZ)Ehh`hrKg0zO<iQ}04BN%vGw"
"q!gbon%hc`NmQ4)Ry8nvcIwVF4=G92v34)L<&zrpBuyk4N#Z`k%H*nnN#DqX<Oe{(e_FV`9w46C&n|+}!H_)dXNLrowb9eLeM&vJ1tot34P!4XoiT>lqX*-N"
"17MTC-HLa4yy}xq9I<=9R?X7T5=^)S6WPMJNK~LVt0Au((|kb+SA1^1tX!Q_u5zvBlNYCOl-OO#br*G(|Fr|346ETvSo>tVq?hmtji<w1HZl(>-Xw!nNQ|9F"
"&6uj^y9y|MSXR&%Se<qD=3W~Y@4*^(4vbyj&9RgCTgj&+4?2#Tc_B^sW?@;JdwOans}hlqQ1wZol&qkV>A6eOjCda>->g8^ogWm8?S&!VaFfIQZA&#H^VMpk"
"eM3<s5a-%qyjW5F^SjEvxE=Q|X%E1u@b@votN0^~`vcI6dH?*cdQ>LEOjKH!9zeA~nspbtY}8ioM!TUnrouR;jN3MHKjv$O7vuJ1UA@$pGMglwZhokc>#YWT"
"`dI9F?E_a%(;IC+4mB6z$As(}e$M7Ii5j1V(2GOfA;}je+=KM~GsInuwb%0O3CN8zyhml#{`=euDTSFtHJDhj32TWmibv^X=}{jwLymRxfH0dn@bSUpiSqfe"
"@B$d;SzTNtHH%fS6Y_K%MT*m7=<fr|BK6vQkJj|E1D^WDu%;x9JRJkx4!YB;b`Ht8NT)cEe~fPW#UZ|GMIyTPdK(Y*gM;RfDc7Pu3sD~Zb_Ts60U){5M!!t)"
"D@B8eP&8j;n!2DLGzA(--?SA)EM~jymOt{{;QR$gIKWt+Cpdj{ah50S6R1%{Ed2<mQO<PUqY$fHQbm`(=|ccK7KTD|UFI8+MVU7GCC%xUq3=BlK-Bm8c$5u)"
"SGm=Is7ky8U=l{=%C73%8{#Yl00-|Z`t$hDY}-&Z5g!+JVfRf?wG(QFq8{`{=~)-$&890bcO5LwAX4$pk_Oi8QaUB6vjq46p}=7`g37w7lVSms?xjbnjCn0d"
"yfU6y87Gco{{!08Iz%Qbb9|HbSAn+Mhg~iz(B6U(P`Wh{py2rx_}4ETE12zV!(6k_<N8j!CNKHk=6IQ57>!wiyJl<ObzmX2ub&X$Ii64dGyiHJeDa&9Z~Ud}"
"&HwFP<3$zj;K1LBVx>F8E6H;S^|rUh7qp%uYr~Avf0)spsBEd6Kohb~+1Za?@KQLBUaA5S9h@6Wyehof!}C&1rPL9weY2`GFxCaD$(mb!m|*qLFX$bDAu04s"
"JGPrXiL5a5gVeK*b~Tw_4$Y*mmG}vq)~P(n7H&2G-mk)>lsFSdge`|BQ}><?HxZZ+_!WI?gx(BTqG(%Ps!_IzvEI+Fo=kqY#r_B0V&HHrDQWw)6v3WHdEi>)"
"QEcf=r%8S0l@l4qWw|tLA1`!t*C#916hktY$X8_#7hJ(jctnA_3baTy!@njQdw#M{+qh%@Y;=maF@6)HUFwI9h*6d6lm<jUMx0}pK#YQAu-w2XxL#`N!R7@-"
"XwFn=I!@+^716c`ZZ@~LPWtkGl2gz-BkmD)YCQkr#k!WZNe8eN2*p7*J=iQ{Qt3KQk1suB&awuha?w`PY+`k_Z4Mxs*QbZ3GT{*8q~bcjtg!CKDSR1}hBT@!"
"MmAPP-<+X>r6%sctamKj9guUMCw%_aC|O4@pJkS#<MT&Cfftnh3!S4O&{&{!2tVHx#&xYhcEZ-$ggv~jKOP&GM%hG{@*_U;wx$9kikaB9N<~=D^A6HkfS@u0"
"#C==I1nEJu%GNLNdgeHt;x-F=nP%uZ8VxxOp_QbxkUX&|n5sY#bAA4r;1j-jkjWzFtJFGBPPZKZoR6dSAFTd+K;PY!t9ecUi+>bZJ8b{+4B=}Sv)IHkRd*{3"
"ap9vxyHKH*CqeAONSa-V6;qYKQxOODLDH3eJ6W%(w&#RcO(VSZ$iB)<hxaRB$r<bPR5%?aBW!rGua*`A<MqZ2qxh$Dj&n+jCqHn0M^+Dan`3yKikoo7WKSz@"
"NHXzhbY60`k(WGh&^Pw^tzh0urK{>KA1rgmgTcJ1^&EF)ano38G(RiDPZ&71*(}ggj{#mHh>Zm+Y@*D+e@126eTPrZwSzlxp7$Jfg2P&uGZ{e=KBkA)%JEL>"
"Q&I05%NMbn;|6D3@7+TC;{}p~xm_%)I79hJU<GwcnvrHrUkz6a`(PIjsdXW=;S=vPq*fDvC%7PY1L1-w^Al*~5}0ELkz;q<h8RPe-Ra0r2wy6_=ob5<Fe2MI"
"u+keW5ptN!?c=nqlfm;}ZFSJ)_JHE-N@A{`>J(TQ%S$Y`m#WFWO*AE0n@mxG1%Y1HrlOiO`F7Pv*VpD<hfPX3$l`76)S)|)2YkE(_e5UIPK``wQZozi?Amt1"
"=rsqW#@$b?qWJ;BbE$R6%hCmaysD7oi5cZ0&EE0C7w9|tQH_kIOPpwD25h={DwqpwLy;1MGNoViFAFt~mjH=qMoVrki*#pqk{j4ciWa7fh#2f$<=AqC83eU{"
"?7p=r+qB9}#xdxoK;Ws+#X7k>RznUB++Ug&>f8QOq(7OTNqGwjl*p(RNUMI8K@a-bBm@OAy~jXZCqKw@YpJ3GG@5y$hEdCCs?{#R=AH9)5MnIJ-HlJ<H1xGl"
"jcFNuG(1?do9>w=f0W<3tu;M)t?C}2HL~_ffWdVe!zYkxRv(4e@D_!SKRJG1Y)!z~m=jkyr~-iL^{*R&{5k73<fz8OTM(&u!mwvliD-XXq-y*>NjrdP87&2J"
"R(Da0;d(w5&Y6#*x0ngaU@7>ep(EFQ$gSZ6P-1T@orJc(5;6(iwn);x7Ozx3x2|!`AY_Ta07by*7nNyaMs<s9UsGoNRme!|Asg%|1-|3NFPO+B<NE!EOBF{S"
"GI`g$?nvqofSe`&ibPc~UfmQj+CKgO2J{-js<zG~(j<asEXLkC7Pz`{K{dLT*rWL42UomB^Bs!jMrPvmJyp7zPt4dFx8HzzZ<wwR>H2nVar8;kAsYY!erT-j"
"heH~GrW`Ms9rW#FK!+!jeioWh1uky-)%S)1uru+TknOv6lp3pF%pW<hAY^KuyKs!r;xDoct^{t<R}*JX-1DmO$SNJhlg!#xdUc<2ZK@Kl4638TMB`6Ht>Rpf"
"eT!)8IR7IYY&2Oe7GQiePnk*UH3FP6FYGDqQ;I`wvT<CddSICtjf}E?g0^s`S0|E0TEEMRt0hcrkiKB_r5Ll)_9u!pETxWK@xLy#oGIfmfEAgjPF!0vJlP8c"
"=++DY+(*mwMR0o~>C^w`$!=V@*Xv#gf^Pd9a}i%BV+wUK!_|O>7vWgdqZObZkft8l@wTJI*N^d4`>wJe{0y!I)cSmWsU5%)UEv-rz6p#Zsrcf)<|>9#2mzk*"
"engM^7QI+&%?hjFg{+7W|97L(X}wo1RuF_BXkgeiZXt&_&1GUw3Fbx)?^*nZ$xB+7hl-^a{!X$DA@BQ%^><yK=zYxy?q;?|EN&^iTwh-Gq}*rAEjTWUp@I&U"
")RmZRhB9t&UaH$-xE~K=m1T?%Pjpq<h?Ste8|4dvVz?7nX90U3H`-*#W7O`1f*xV-@+YtB^nwsC7O0`(M6LJxsIeJ%mbJu@#xZEwU2bG(HEOjgZAjuvnhZ9N"
"kR(HyCq&hm@Bn42xo}9D;)}Te_K(_(UgcmDX@@2sHHH9DY39Ym*sreihzO&1pU=$C#qgB$p<W7O@%`VSBGmWWlxCtfh#^rkFK=JF5&txWdd}TvAEad9Nju0D"
"@Ze*4EkpGc)F^yEr&vwQ!#)+Pc5!%SyP84>d;pgAz#%$`F)I=CkkWPCQ7cMTg^9fu02=n;-*ihiQO29oHl@3A>q4Tal!YNP7l$F8sw%2z7ec<>$6}Uiz4|tg"
"G?maDOYR)^6#n@|-ka<E!FrWz1ae_bpfKS3fQ^!7!=dC=o89n|6`?b%tc*#6pO1HdCQ*n~IygSlLr<zhlxJ9d_|^V3LSrgx$I-X~yDUI|Q)!1A0}EfZWrTz_"
"bLap|H^rB(zbw7SSz!$t@7jYY7dDw1ZJSaqc)PV*M=?89H%;@=$auy_7)oxS%TFtA#`S$$lV-uZH58WNBw|(T0^O)puy)h@w|LZ?5Yq9eko&xMBhnBAa|gnW"
"bc>Sj>x)Ai+Jt%HLr?@xo@5CjprO5If_8jAgs*8{_nca+7WXC62=}HoClJ!^sJv27<8#6zz!vvd$bsp8ZDiGCcn{~MgN;Ypi+TwmHehB07&uT+ZJ2L3bb8>S"
"#4jxs0Yf3aKE-cBx&syv!)Q};{H9;?Q}**$z}H_3DC0~G|ILh*T9f&b#6XP8Q@!&jhz{P7ti6r^5<eW{^X$x_E@QHgWA(}~Q}O*Z<E42Vs&&;nrG(qwz$7p`"
"LA~n(CH1=veqgs`pi(EP*|9(K_|s5w)3-T0GIVt>z?a&_lr03D*;gUN-wB4fyuc4bt^%;DfcL{S&IxPi_b%7ssg>ZA2}6vy7vZc@I_4kkdfdZNd<I+~pnios"
"wY0Qyl<@yISfa|LW$xg-Hi5*R3{<c-xD-Oh$jgZx7=lYvMV$*W$nD_`S!ovUA`JA&V<~c6Z$2V!NlTVk;Qi@)auCc-@Zwk6tWFWO8izPLU%~Sw0kdecAdbgy"
"FNmJ&$FZ_aDh1tXnkQm$wobBg5C%5fBYE}IEdTp<r7`IY=;_38*~*J5@>b&j3PGK=r!lwoY5Y>mm2B(x3_njG=3p^8PqFR={c2>LXDoNxVm7N!QM8v3m@+lL"
"UIb4l4>qTc5u>jUq;Jh7UdB2eE%Y>q9<$A@c=8bs5KTn@2_W3XU2mv^$6-xVr%zhET|y;Ap&G>W-lQd&W)FDzUe<z+J|If|Lg^^tTUNz6XME6}3eG&f!9Ke9"
"?>*l;+bML{I2muZ7$4^o1E~q9!p6V4ri{p`8ix-?$o&lOE_8!KzlWCaFHN-Z^`i(k52h2XMx!`(TQ22ThEOJ|;|y-R=i*8heoc@H=2#ydj)6(1k|SRUJRzto"
"biP?Hsqqtd)qXN@a@cnFm2xOqbtT32RdxBi`A%VZD%`hDp5lMLP;*{Tx<0<nAh|V@U`(T~P*~er7Jatu7eAwp^k>H;!Ray1)wDTa=&@(_-^Q#<w}rRop2c4y"
"2&d$QzEh0V6Gb|1xxQO;CM>tGyA^%Gnn9Ez!x*6S<G18&xa*|tr1@-W-!o*F{+Vdl)n@KvX@)(MJ&xE_k>qMK3DMV15;RS1b`BI1C4k^3Ad{!ThJ3g638#^6"
"Oa)+XKCSJ>bE3l`VY*{FgBqg0%-iFlZ%L)orde<#`#tu)G<xm>{znPJlTMlQm15<b%=e(4qdN?s+RPDis=!JD#>tdgD%j<Cc(u2OwvFh9sh-v`!7>`t1v8XK"
"s^6j1mK<;9<c%JThzjx8M?}l!2sxqA2XSSxYzCpCrrY#hoyoVIZ#r{db5B3bDs^XC>x^{XvWd#mYw^b^T$(hiqAL%eH9aW;cy9c6e-qM)6QD6z5O5Sh@Ek>t"
"V1EcwjCf4dW+OG;=!-M3jfCjPS7ZtL9(q;-STe4v%Sz#EIgU#OPm*rpa^|5%l6xUB>O=<i*urw^((_=JZC(!QgnNQ<h+>0<4;Q9bJDJuV?sb0=DuO>@NpyXo"
"=MMZqpNdASRr#-E7{~=s=q~gy8mJS7@3b`h)8j{T97yBsK{2uX^6W6;g`TME*!-{`>!x~FcBIaQxthnFj*(q6gf?C?{2FLZX)-Hcu<zTd7~~NJ%!jE)6BT$n"
"!)~ox2wAf=xnB9@u*@6XeV_&JDE~aAxc#nMUt%=?q9yA(gDmO;EW8m0jvkpNf~U`wZ3xRjJh*Yvq+v=}(Z5}nUmSV;ktHeq?IO}Qc#wRS`yvDr>dsRe)0Tta"
"K!4_M!Xw|^g#>QR*qH`G^>WQ6<XfQF*(vs;)j5t4e~JVYe{OA_rj8yaoCZ6|cBr)YBoR5E$08U-KvJ8)+cz?HWZwSTA~Lj`d9xKAj8tb)#;DKYhAWzp3@nH>"
"-QTW*tUMbTl3<sdVsRJbvMP2IcM9MOMo?4m;sO6?xK3S&QTb+`>S*XztYp-V@Q;nw{ODsL&wlgbYp^Z26ErM$Ahj}On|qNq1{g-f&1z<Ga5_rw@Ul;3>B=yb"
"=;&ptwA){N$2;`<Q#-_Fft(@1Fl4=xZ}SXi=&OSR)1hlVn0r3i&f05wwl~5OVmbm9hraT2%oKAIW|4J@=|y<H)r(mI9lFQSM5p(P1aiRv0&b{^&gpn^aBJF2"
"*-^S$OJ~xJI2y=qDP01-!PHpvow2?Ys~EL1b8+7?{Zl5Ek!wy;zd3iA_VL^DcIHvVWqya3woZx8?D2J}&|$XN3K375QGD;pwb1RI5mghgVpPNoP@2TY(j0dl"
"V6Er@DE#@&;{yY~WV|~wVn3ZoaAP&+GzMqR1kCi+38z~mL;>hziA!Wg0M_TsFH>vk1M_2a1BSG(MapQi)s|l`FEto!>4jD0eJSbKP-H*TQ6w(|n>`)=pXQEs"
"$2hnr+atYemEYh7|0PaQ_L@218+wTgHaUFeDD;#o{#&EkvG}UnMTGVi*Lm6U;Zjp$=JR3;hZ}DzA)Z(78}036Vg>|vLpks(^%R)m8?Cm%s1gs)()UqMIXB>A"
"*&n;`EsWbF#C=Gt;TC@`mvGA5&dt91gCDSF0hHDxd}!s6a#%cGM=~z7+y9?g2lzSkJb}OrgpGHKlUQAIwMx;U7F@C98Dxn*Mb6l$tAJU-G80t3oUaRV2cS!#"
"fd3jv;wcEVVL_tFWa)J!{(*^FT5HQ_d%opGp3^7o)NT{r1K1=JG@$G+P2O(3Gs9fpd`A8BNh5s+x2%Zm3C~hPX14Cd5S|`gQMqYJTGR#6+?(v&H}45cUJpmc"
"cGE68cG>M%OAHy3+wG--%JEtwN3hH<QZ&AH5?=zPlLap|RzSHe9b<ZnZQGAeaSG9^|E>^mJ^q_nZlF1_sI}I2&d%F3TN4F(H#iYJs_O8xZ%xV16Nil4fH5An"
"o<gFEtQ&zEz;@JXJmJ2mD>M!Ba0>q2NJKQ@N@|2}`SRN!(*U|8;E*0Ib6JV6Oyw+ASpqyvz|g(R-bI~YH9!;fny<24z@l7JCSlG&%#GvfcEWGDEYLB+(>yIE"
"nv9@&$u*KQjgzDAh@&m`VCX_rXY9Q+Zhg)-+TmuJ!?C`tE7l<PeEj|7^a8$6Rf#|q-l`kZ3;9qsb07j1PRWxF_f=Dg??kpT3*HP4QmDr|9QiTu-rQdyn+VLK"
"^qc_wL>iU5h+?nQy{074@6wHe;`pxXzf;am<fc`2|H$Tq5E|j#NYwWlR5mne*(+XZ5hwrJ%wwd0Yo<e|zH#EyjO2`0n}Uo)IYUN1gpC~%r<+W-5)FZ55pylN"
"3IRK)GKH?4a91HqO{P{y`gCSkT7t$TP^7`7Hh3G0Rf|&YG9A@D|6!>J&dK%O8#00EOSS_US()X&pl{CSg9Fm4p)fqQ+y=Gzt{X?o1bYz)cEV7Ivr~!;QqX?H"
"+K|=|bV=Kola35X<LpBL7{2#}fb{nR;Dd9&F|B;L9M7>!c+IJlBjPdqt@u!14C4fJ$}kMY`}H!bfHeEr4PMIu!NO~END3}*Q5)q7Bqy=*M1O_b?7|4o&F1ma"
"*7?58ya)8;>I^CY1C;QvRq|PRjci9`r}%bUFT)@nDYu0(1rMVOYsEg9)UmB)3!Jwoq*o6ivU2(;5h!#`g!?`L^%lqTWJwT49f$n)GE!2PIL-$r^DY=aZ`t8@"
"JUS)vS4&=`^+K|gwVjMEsd7m<{r9BB{$K}ZZxN&WXP!&LHa<ux(hCn)+HNdtIJ96?QFEYWdq2TBraN<8T?a6C-OzU`CfZ#{-DP^>I!j>r7HtF6oxgjBWT@Z6"
";%>oiVdE6sgYrgE#9h7cvy>E;54YBZ%1`sb0Z6>@C8y8d-^=a%OSXK?e4K{IdUga1Um(PKo3znYk?^KcAe-21mdvx>;A>CAY2pmQK<d~|+(g7(PTV4-ofPDw"
"+Soi_hi`HZ;*n61iL4Tz$4~^RIvx-1XYp9<Gb9NOv8HB7>{1`icN!I!_$2}{j9%Vuk48}bt&%UL^N)GQ62dYnm-@YWZ~Ns>O)|N4A@T$XBVJH!jc7+2H}Pf0"
"TqFetj!g&4AaUR?FwaWsfXypw<v*I+{U~SrvFcc)@F#wSJj~EmJPIv<Ka=zfPz6p@Yg10Lbt5&?D}hL8Gqn-lfiX34_Fe+j7tascVG6x{;j50DXY<JTxE!cs"
"xKp@-Ly{ZLCzUmj9scmrsmcgF7*HrKJ8kVd^AbNii4D+lCe-d<C=KLQ%VQV_L7xqNhwqU@oEH)q0sh;EMr*%%v{h)<UP|xq_+PSZ*58CjhF3i=djYz=_j#3#"
"?lD1Ur+W}Oj(Fj=<dOr-3{Jx=ij$el2KOGV?|%yL8)ww6BtmH)$_*UPMAz$N*65W3*NL`3$5LOaN^=|w<BgWaWlv-rR}8_c>yAnBD^y2IH+)f&(93WqKBXiE"
")*8&+N$9f0Z7gc*P>%s`teA{g<6ww=&MJ3qmc^*?G`v;L<qnD{3gW^O$xA?cBSIZD_BVzYDmGbZ)8nfthu<92v1)Be{+jC7tEPTdeF5uN1dZqM3-eizM7wt_"
";j##6ph6Sc28Ga>HDpm)4LCF)_{nP|YNhAIv#)E%Kt@3Oj_A+CXe8340bpd&{G<VRpnpw6smzQd6)sMNU)TOqZi`;lYoZ@Fl8{vFGm3a75lG6mml(&u)CMc$"
"T3LW$-`Y0IYUAt6HrQgt8_D|kyZmr;WCo(j8A+Q!5sV9gW%HP5PAJO6^Z3P)htP?~s8cPD;xTZC9J6tIZ01*dz${g|i4Rf-(mjy{=-OXnxqRJV&sPf^_WQ<<"
"IIw`sWvCa8muSY~f-6KVOVd2vvtCDwyN>X6jia<36_Mx7L;TFO(xK(bUsVfa6geN~@%ZFeYP4}^2lb-<1;c`>^U7l&ZX?z(0c95P;xX_CQ)kKhipJ!<MML?`"
"#l~6BIlv`TEv6p28%U7WB);-yZA6b=+ONG%VJxvr2uTZ_8l)*DfG-&CS&@~CVu1*;UhzO&9LsoW(u6H=X@E-hKB<B!Y@Rr(8UW(<XnX742=RaaU3D0ohQ8l*"
"Nk;U!wm|Gd0rb#8TVI7i)*?hN%xy8xgjB}dx<}%J_}%%v4-z+7PAEGr9V<9Crp@@rz$NVjVh6K4ja+^lWm!Pm9*HxLs@ewR@VSIeX(#+bk@d9NrTGwd<Ea&!"
"X!L9TWzccv$5$2Ai_<l~0-Z5@({Ei4;gHITNs`zO7dTlOksBT5dmR$g6qUZuu!?jErX&WVUp43equKG~9BhbK*Ay$#vqiIK0Y-YHu`o^I*q=GtY2rk4c-(S>"
"$yv<Zklv&jLs{s;9Gq{RYq5WBi5Mn)>H`q9NA3CCPeU<?8>$8dCwMHbA!3^Ifki7J|Lf_*Cg{oS1bl#&CneeEG@ZI~E0vS3p%Cw%Ogv`NEj%}ZrB+`HJBvuv"
"93B_B-6Knl@Ha&~l*0!9e*XbPrt#E9p>><sgBp6KUGEFO6?}9Eg_nbluq>fSo1TE(k4DjGePXr-(#<o|DGwL|?2>Ia*Kcv<IFIzB)nJvY8Gl|p%6^~XXH6`Q"
"kPU0X3~|AFbFQ};hhiWNtesf0afjxo1$%uGOCz#ng>zAI|9<;9()h?iA)(^*fa(3uwn;-?J1_sB{z+oAaPdd+<N<{y(q*KUBl?ECdK^4$T14g{&}L{0V?B?e"
"^xID_^BG5nm!zif6F{_1Ud6*Muk`cViubEF9~Jx&_V=^r77?XED&exjz|^d0H<T<3+6K0Gi%9N=C7?B5;Z}#>bxPs<%#lW#-1VXnHCTgOR|lvZNFf*_eA#76"
"xsP0Zl8KDZY7j%n^0`E9-)p9`<@fjCDUQ$<>hQ+S+_-TviGDQh+oIY6&_itLlGq6}b#JRK%FjUEH7GN~U93m^SjjNwivUYjI!09}qT8m^4jOwv3#WrHEe3S6"
"9ynVwLuL4eKk9KNV4KPL{qoQPuJ4ng{>z9nWgQR3sYYu$^aHr-PO}ky=$^`^IL8`JKXalbCr-SE0^{DoFWI<#qWbQ12rP8^u|s(W2$BO-!o>8o)DsZyt}YmU"
"|H100cmJ&1li!-89LOrrz5&GrnbF>S%ApmZJCA|yp{P*hkSChSx@c8a)_Y8WA#bb=i;ZSm36_T!xv3og(5dat_>Nsq_hv-)6E|Ckz)q_>c8YL2fnj#eP*w_|"
"_h$I6v2@F0WlTDK$3c2GlGsAsq^c=~UtlC%en!DM`>GV2*8(qa{^sJ+R|+Vq>fMqc5BJg*l^Hz86C_=W^Rd$$EYpzP*r<|UY-xPvQvBfx6ZQK^(^f_R3mVuz"
"R`g}-yockWRp#Dnd8Ws2sVl#+gZj_p3(DmJ&<EAouEy$qRs){o4Yq}sryDCsXAbok7q42#uIJ`e!>4iAvNKZ#u{;cgw&H~(aLal&d{QR3s%<6xiyMu|&EYoQ"
"#P@oC+`}5-PSNd^WVh9T2oKpLu^F_iEZ{fU_Eh0GPFOq7I0#?T5xOvm7ZLqaJm}_`1{${<t5%B}b!SyMbCbU|RjW;;7RzMh1z?Z0^!!a?R>bwdM@DXyE@Hy5"
"CUzEg4#0Kmda$Fh6O)+T0&SU{@RB+h2BlzmABuV|`0vn|Fa@V(voIE1;+E})&M48P7dky*e&ai==GHr{j*Uj!UZoz-Ao%XqQ^Wh^iT7p84HW^J_O<3KNe?GI"
"WsJ4e#i*k?oiEx++I_+JDkTwwof{p(1j(Qq`kRaioKL-`@--pC3q2Kh(;lsulNFVbx$zft9PCkZY|x{5tL~Bps>2JA=NA&BvY@|Op5zaqj$6tJY<PUhRlXie"
"XFxZ;@^m3bnpteeSA)&T&m_-{Oegxv$?jtYdF>7@@s$f1>KN~i9v(2e<~b(D+VI#RtOREp3~Yj?mNI~d3e@CQxHOd^lH(Ig&sag3gkAS4>p9S4Z3Lixxk<Vj"
"W1jt72l6MbP-R&uj(omwfEEs6=~##+^Q86=N?bSDkPyFtb{Z)1avPwBowl@3Q8ioYRKn>{jIz#>PIJMg)9rA$SitLCMkWOK<lye^o#nAo!c)5{QO6nYGKT3%"
"w5pjBgrzD9OVWDr83F2GPR}<fpP)75yW%;_M6+#Uprb&VJhE#<lXjv?mN;dJQeu7IOaIcVO=KR-ceFMMn$;V?l%xpO34RP3#gs7(`4VwXL04lH#?S@fR`@k%"
"T)LT*9kBJ)&2IOgBnl0;BN^h$bMdl!2UXGWpEpsQXq5_6dn21Fc0~I&CNu0`Gkjj^nXi{{T5M;0Uz1QrSbOZ@LBPCp*v!Ag(bkKuR#&n(tj;i&j{R_0e<OhA"
"nr>x|RxGmy30iBH1rMeNHn5#R?Jz9H?ie`a!^3+aBe1*bM!%v}I$VDoQ2saijoEEH&%x9Jl2xI}3T=Q^Fkv96A%0gn#_i8#OuC+(nq!IOAQrm+JSK%fLi^bu"
"hM4;i|9`gDMzmZYqi3)T^rj;pHBnTwZk|)aUBN;|?)Z(gOA!kvL`g`#RO3ww>l}!z<uK=jm?i?ynWkRNB21oi;KBw@&rWPLS0dGf<bT%9{|5qyclfrGm{6}|"
"V_GADoQMjn_<QhO-4?DehCi3sXJJa%rt2bN<D^jy9;YV6+$Fl+#+%G2@Uooi&k<+>LCHDb4o@RGH)49L2c%BRn6n+f_v}*HkY4Bz>iU_k(<k-HalTL%ud<*}"
"pOGRXs&1uOatZN{4dAdNu)l5&3x3Kqe%>NK7QId^REQ!*gvZW{_<d7fJprX?lQ#A6ruXz8RLJ;+JdhR?Ve+((A-<=tvn<%@gx~6pGgVw=$KRFCSZX6Kr6KS)"
"FiOmR3uGtYY9$RtPFNv{9wgrEAq`BJOIPxWOSzUa2Td@XdA45!DnHC4F7=)ZF&}8+ke$ACoVT(ddW~p9l+lykDb81BvI(g_P|o$2ygdpMR4V?3-(`J!s(dk&"
"5dxwaD{P~Q4SyGYW#;dYUHGO}mQUTwz`@u2z58m;kdIm&)XKCwAB75S$X>)I($SMwI5p%*=o%W;oRWu$L28cfJQHp!1T<1)hgGnPckJw`TnQ_M)^`3-S*-oV"
"V0xE-BNhSdmTX*NRe0JO@vDg)gwPj#+z2SN-pqGOl0b*G-Iv<k&>H8c3fo}9Vrn*^zx3ST@~E-GLfZ1&sN9(|5q=McM-^oLyy&5<<L&WKrS$?(iPEQYs1lzd"
"vrR`JXte7WyKEkT591s{w}1n1la3>opsih$Ycq7QV{~rSYWgHifRz2TfBc`GD^51}%ZqUwOq5|rCZ8)hi7~q9Y}&Rmp{sE7Upn-^AfAS;iU+v72^a0A2n+1{"
"w4IHED4)Qlm9<|fmV{X~QBx`FA&Lo(NJ}7V+Tz9DJA;2aHBi6bjCsbPCxca5?ZtwA(O#;$?=(f;EE6)f?@FkpM+!M2Crp=eifhf$6*wmmZG9#w{dVE5JP<zW"
"WHUYs$lOo}GNNl#o(6-UGaL4ibzQAC>2L(6r_aW<Jw=!xP#KnF>SM>XhqDpaX1`j^`2*cK1Q={jrvOGyJ*+(zlWr*Ify<s1i!du=SmC(a0r6tkl=!XH+Ox+@"
"J{Wd@UqdRn5Ye;recsRD+w4fVFR7_czB$%qk7x_*EQwM~iYsLX3sx7Iwj^uN=zF|DCdB&q^>pW{VhTfMjBDVKGV^7~jCXJsuuo&eF9z1qdD$S-aOx){VzAm<"
"J9e1JM1-pcCHn#+CuW2J4`vw!l(<sK27W}Qx*!KBV=VZS)x+Eg{&d0Tz~{}%o!pX#-DmXCDM~EW_WxP}Z=5+5uw%C$HD|}F76#N|Cr|QEK>PlyB<AF5<R@TT"
"NfdO|o`S9J%Sa?_EjPkRz1bC_{X9FyoFm=%8SgoBPqXEUmoAcq`5>$~ZlK&(Y~N<skB^Ge!Y6LbX1oHK6?1~}LNT(E!-m0Rrn?i}m4!z@RZ3pOq#|lm4p|*l"
"p7BU*!63br`Y#n99aD-u#;=ny7Xuw+3Dtn6qdl>vd^td<pFHvel7lRN<t+@IfABVPqwAr?m6Qd3j93QoeJ_C!V2J5LDM?)Nm!yWwB@~Ixae(Dpew%k;o&>AN"
"xy=u-k^n3fTr>@WYeEFF!c<tk;VQ<4tG{a%mjjECV)`iL9FUB!l>jAacmOm~)j6tBLSgl5xTwgG?HngRdCiQpL6X6|vDwW>k!c#2<Q07TUf=^X?IMUAwJSfA"
"segApt(f?JMa7Cjz#-H!(D50B^Cq;>SVC-2$9ocwwXZ|q`5$70%1X1l)XNofU%Op`8JG2{{&%mZNrCFE_WxyJ#iOGXyWJWO)}Q(hCC&U{E{1i<Marh1sdP8Y"
"AZXR(YLq7x(0N(nGXDeu$y?v|JC7iUP3I&*R1C1s<kg8oB4I*+o5+3y=Z++C>kavON|Tg1sjRuEeSlB^f3X!uO!lwQNKW5h)#E0v;hIvLtFJS)Mhe2LFZWBH"
"Fi5&Sq`oX_Ey;eWM;n&gp5vAAXCk!CSIYgbEEL^6Dh;t0ba4dxf=XKQOpjYX?#ZJ5EebuZU#A6AnGuT76ghxx-}sycsg(LL`oxB_=iB_6OWClT0OonkS3U_q"
"_+!kl5h|LFu2u9i3NjgZ1GRce@{D?V)m?Foq{&jxX)vT(E@J67IE?<~pejT@tF|$Q40F+NLx`tZonf&&2KN{DW@$M%*_UmIWM~3xG`1AhUywjTq;);&6943r"
"!;eTyxu?3yMx1%rqH_qB`41PsF+=%&G<=C>E;gYiQy|#pU36~Brk(XX;NOho_D)l&zR-~d+h%7ezmDzlt`Nr+LFbH{I5R*s<oUtu91v=Zi0?P-hsv=?Y7s<3"
"F{cqYFD$dT6=$w_y^eLG<+E~X|G==*RB6K({$t&bqVc@QJnywySyfD9>w6?nKS5=o6+bR(KII?au7gYPY7ON_E_i`mI%M4Ek6uDwQghRS=RrqIOj2gIhfHv`"
"5ohr6^j)I1sP@NifG0HFUa=Re&OfU4BV({B`)WAv=pe0H%L3m;PP@PUn1pFs#PIUjhNXLfR|)s{P9H!ys)1S{E<pC~C8?!e&JxiTYbY6#0gd)A*^kL8Q|p4m"
"2s?@8<f<Ek=YZv1wHhc*F)3ol0QsqBD>%Xk6L>n}&$Nmg%|34cn>MWvpWF{-*i)V&LO<jN)|4ILQZF7JPDBVgJ*i9n*33@ymP}_$nsA8;b~?F#b32j35cJT7"
"%;Ek?<43SuaW>&=#joMD=A3wHQ8BtuwP-z$UX{CIUZFe}>SUoD21l&ug{8v#DM_5Dhlr6AkP)HKN!FG;6H%vl+(Wre{J<@y8`Ikwe(Vk+zZLcr^>-I{Exw{B"
"?JnTis^pGN?t*5+!R!)myD(`x1yrwAuC;0SU<A0lBYSmp@QI$Ek%k^qXu5iY)1Nn7tH8U{fBz4c)(Ht7tEk<yt}K4bDp6$~|H4};{x05+xO@cT23wYBOyj1+"
"Sv=VpV02k`BS*k)Exa<400B+@S$Q~06PG3aVv-I^Fas6Fm6O@;)A!EO-z}<Yuu!4<MH8Nw7xreX8vjxRRpV9-ru9VkcK`OA{P)Ip4{P)DeRskc)l%ojQla)Z"
"DOPz(nrt)ON^E%VcK`T`@@`NiN4lHE59n@Fx2>qckb=crSwBB(*$w?O((^Pv6v$$qJwF`OOw^B*9>=-VN=yqojb+{n_y;s**piCo39UF#A(7*WK2n6GR^~^3"
"dTx>;9r20q{o}Z_U)LGHY4&s>#a-Z{M9&Ii0`R1ZF8_;5G8XI~#)bjbp%wdMzQA&#y_5Xi`Gnk+ZzFwhN^1KQR&M5}=b?s`)rK!J^lC|^9&A!vcZ;TJi-Hf%"
"<iwF}vFyk(7<aWYNpq<JFA=73hoSRnGUIJmgM5VFJvpfVycQN)h8-+r*LZX+z7iHXbnL~}%8WDE;<&vX2T(pjW&GvuW+r?IH>wuvZy-jPo_KwrU2A@pzXs8w"
"E)Fw9T?J>8VbTbLE<ufX{ReXIq4Y8uVO<of-}nc5tXKfpzAE-(SK@jLhOc+Xy?|$K=shQ+jiK|P#rk+$0&lF*sE?Q6wqAt_`af?7sHhw^+9YW^RviQA`K@QS"
"58_RG;<%m<84M93K=9{^jw5cw^++t%X9M|t{u6RiR>7a-2$+7V)-tm-`4u$oUb$xAJ&Eu7Bon((DEomh5(#Ny(i#Q+x>Tr&g~AbDVn)VVNuHK=egK@6Y;uZ5"
"?;f00P-!3?jMDbho3*|uIq|cNxLMWJ??MsK#%EL;PCsA_aIDn9b<TFmm+UPO{Efex|D=>lY5<pRd}$^?>0%)6?|XtTTx0JorRsNLtV&P^zd=#Kz=sQ!48znO"
"E~f2Cxf2*%(18~uBX(lew}(sbNja9;<H&!W<!Xg@O=_NDn`kq*H2YxfrNwo0qo)vAmh9tn49UhGXKA8tgt~D*UfOI<M}_&lK;9U+msE5^>!N-08Egwom^@|j"
"om9eozAx^0pG0`ix@fT5w2nh4nLy#8(aoo|utO)F@TD=p#MEG{@)+1&K1+3fXWQtKMhkThFP({stY&&L=G+>zG;mrsFAsgNs`fiFLswzL86Mg<Q(18nB73Io"
"MX1rzG?|YNt@iBdnC2@+m~7JGoTVt#VD#Q|6^MXk1Jamqz*j`40?|^X7JG{Z{!IclfKFM=N*w`~rT`iZo5!rkAuCc?I;VJ}mmCOWG3PHZd<6rD>;PYl0~kjl"
"J2yo=HdbxEjbgr`fw|1-KHN|A8l(5YE0tvg&?Qt1VI|e>BuWvwlOKy-552(pc@J!U)<wcfBGXWx$LaU_HkqAnc{@VY0B<S~3XOH!^cHgQO)~x)Jhvu<YQXMO"
"1|&;(I+G)^mYOC*uIL|q8k%ix6aUvfKYoFd3{YR|VZ=(}nfV3JP8KlKX-v0MK+}mj1MWgY7{QoO9@8oKqq|l<(#u4y*0iFPfu-}|jP&)-Xl*%S(%deAL?NnC"
"*n&w}OVzy#&ywb<d2J3!rn*y-M#e8L1cUUA28vTQYra|?dw~GA&(P^1hi`_DrUnI8mw67Hg_%LC%k1j7qrZ!SaV4e622L>5==sI^(^mJ_*0FPOI`AI7fcmNB"
"25fM8DpP?6d?PHdulsW_oQ>%icC2F)8_1)%J7pWDg8!Jrv%&!FTZ3qEc6nFky{tun0*cm~-;zT7D=%7en^rc~EqPCsy=%}t*=4zu*~dc|e$R!fN5O!EXov~b"
"O7iBOV;f2$fg3z<G}P84-|?fT!Ab=3T2@MB!%w0-?!7x_FKrO)Er@Xo2VG~;MUE#F2%*YImP$U*wG9NvDPPw_dyFqpF8i`44m8aX59GFO#{OSZOo<~tw56Mm"
"Kf!us`Sq(51fApAYycXjI0FovQPCeJ)<K$X7WRb#<+d!!RN3dpdIGTtr-X66;LazDi}et+WXFLUluq8B|AZ1tt*xoqG_sc={i)B5Da5dphB#7(OD~`&B#A_J"
"QG5>}@XE}^eI1O5_pzua4PDeW_Y-|N@inUyDrxz?oebBOjMKpj07g#D=QyBYhZd->&*tK@>8urb?*{pr2CXRgtG9`gyHuZPi9MQu?FRb%4rWL#EKeZ~tsm>t"
"|I)cQ@633WWBEL&GKJK9Ozb*Ke6hNjX?)XK{{B?><8vS(YMHW_s9)(BF*-#|v9hyZj<);zo69}m8}JPFTpnj;mHF3GEEK?53!P2u3@Lolf5RSG;If;?Q`D=="
"n1qyl8wSZvQ`}m7fcuTzaJa1xM+aw<@XliyDcjLv3h7u)ll4NTg{YS1=aTM>K;5tQsdoh2<(3uWkC5R2XS)6Jk-UzR;Em$w>FRJBo)$tz&4rf;XmoHGDB?4S"
"h%Uy<l)r5ZAqwY6wxrPjqO~;Ze^kzx<0sC*NPW*2<ZMTsmB7)`C?dG6zZilHeoO)*jzMtlLD^FTX%GCb!xBg2DE#Yn+@tW?zD~VVLny`QKUQN0yrttPQ3Ecr"
"rrbBj4a*&)0?Tw$Q&-+{*xEY|eta@sVB{kw7zF;I<w!9sZFL;Fu23$4v6A{D%t^m6N49Kj1puanqb820aK=88m3!Q8lkCswVj`%On11dH;m#avxs?ImSSL7s"
"+MR(0uGyavFjS^b(v#Q7GpadYWx3h135*;q1G%m4!dgq-Puqrw=DAfP2oPDt(s{mudLl5+a1G*mQS04`An!RV{0F|n&_ywjLHLemvXnYRHpKqrbT7(2kq9;R"
"o-lv?q-Mo(AU8@oYZsDRAP%KIYJkP|A9<D?|3PaL<r}c5AbV+CNvwnpZ96dj5wz#L;55wCC50T(IS}Y9qSn%m!g)1L=5|1Kw8vD?0w3sF1Vg_gM^ie3#lgQC"
"hWws8#>x*B$O7sEJ3EL>C`MaWTe=w)TvV`ja~HPmvw$4eJAT3}RoMi*TDDu*qiLU}rry%W{4ac*Z;<;(l0PWj;HHzC-i<Z@Zhfajl}Wq1V^Aybe7=u%U}U<="
"#q-a$=O-3^6%Ln7e5P|1H2oal9hg2T_2Ks?6xWaOy(`UE<SHW&HKboW1De;pyIwUo!ivi`X81Zz3P<5@_-61hnrGfP5EHa-{W@}kzEy%L<9GqzJjw52C3m$)"
"T8L%Mw|*dT9gyf+qbcI1U2jctrUE3+Reu~AWZCc@heb>5xslqkRFP`uD%!8+Jw<LLIQdL6-T}6^9Dzx*G*df)4HQ&pL8FIsxAXKyjoQ@g@8K0G!3H~OoyUX{"
"%LK^zub0cf3wg`J0*#MVYiAjxk=H4=-9VepmWm84HwnVyZoFNZe;%(lMQAxu2#+zU#JKM^=Y6T{+W&P^3Rwi#G7fzL==*IEf5nj<?#Ex#Zu)9R*B@r3VVkVj"
"^lV9Nra5WHm!NE=al4YaFgv-<#eA>xL#B+<;;}mDLAp~Jf0*7WDS@rmo~*Q}hhq|EwvMa_WspN}RMyx2BtCc~+;7qrDdCk3vjI+>c9w-1yB>9pML_c+o$M}<"
"d<DJEEEYW99zdMYP0VtC6idLUQW~N9-n*9K!u6E6g1el_jzzKcX~_0IhHhmW#2E{DqvUd*Gp8l=dSMENaSWpP82qe8DX8ZYIuI8P_Kc8L4O{k-IUD%B0=0e|"
"Yu@7>X<RGFMtLcEWMP8fFfVvn^QgD<YQN+eq#Kmq;+giJ@@0qtf+Q?TU5AF0C)3>mETP<2=yZiN5ESV>d%0dn&@jjJMODDgC~9u<6V)o*sA5OQ>qkqEFx9N$"
"1r}&+HrlwZUV4b^dg=bZ(beH*UO<6ayRZ&REA7BsekAZI0mB8hzs$1Cf))UtWtr|1Ql^zTS`cvM6qds$>J?JJ)Do}hA13K^4g*5C|0JlggIvw%m9PMZaSqH-"
"@Er?eIYHxFj(oB!I`4r<TS=zWIN7XdE$YClDe9yRt9nff>YeOmj1RvWY1LOs_Zuyn&9w5bjDmP@GXS|rM~W}PA=Q`Y;7TRgg6;_L-of=NS8%=#i0BNN8SmK)"
"!0e_Nz?q;DqPOEx&dxnpI<bGRvItQ1`ln<{l|{1GwNp=`h{gxH046W>E(G^n{h+Gffrr_&Q9!!mI~Q+r6&k?xf_M#nG9IHec_!|WA*daR{iun%@4O>Wi?})Y"
"oP%y2puG=<5h-rt19y*%AWd*@HLlV`cgo5&BDBo7T6Ah5_C84rQ<p7tMFmce<%pEdKooo4WN_~o_AFFTu04+ZhiW!`p1?+8%qQSdIYtYSmdDbr=JZF|G{f2V"
"R?KC8^I*}noELvK9He`1uQTl4e&xh({;Tn`|9R$@zZIFi@;6+$f!E&1U|Ti1j?m5?z0?{>c2!kyN4&rX`JBgFH9-_joD@vT*S8doFo1~ifTpn#UF9SvR#tzy"
"W=dlOlv{<<d!Qi25pyW|E#TqQKl{)Y`T|wt&9TdGc}_YA9eZRWBSioteyxs4YDGibL2~iB7Tm#FI@A+1hmphTL~^88z=R)c*%j)aPezF=Gr~WB2jnGjSl#21"
"yrSj=GXQK>|K2>BG6%afk{IqODCiSuq+Gl$cPFcl*LEp*DBxj2v>Z7p0oCYt^dST_nE}E-0@<Bg>usEE@W~-XBq(gfdikPPd-Ll;h1heOpzH?mJmjokBpEmA"
"-Y^JVV_J{e>sUuN5pMMA-;9W5Bt~0lMQqAXhuZHumV&}SWqn;u>aneudCFQcNQT;Y>B)GE>R>iNOdWLRP?w3CpVa&%%upBh)$c1c*5zy2cEbRt0G1WhwO^oM"
">57hIfEas}QkK$54{Y3w;@JWUTRX785@pjpB}wU@c!O4_z5`N#if>kPMVmJij>6snQ(vqaB5{6Uap2JgRClQyb<r5865$W4a?Kavd|2_3VDgV+y=+gEOt#h~"
"YwG?bF0h5J*>X)VxZn_?%`RaJrb5-jip&`{G;{SbJe#=&7BXl|NL^aVj<0v3cR0)285nRGUq=C<TDTcRkRuM<q2&FIzhcJkZm&~8Dy|s&?7mMbJAEh;t3XDS"
"fP-HqlfU%5%ewQwsEP`4A&Kc)ne<*h`_;_$HA85y6cv=uR1*?i4?iLvd$<la4?RDRM9}FykGOkOIKS^t+Wi9z%l5A*^!RBTu>@2{YPytQanen@`n&3JW`WH@"
"fz=YF1*H+`I25Xr4csaGu>x6|P#$<_RZ9tUKkDjb4^W_7QB*WmOchA6(JdT7jL$7TqQ@`D9sfL{XpxWC8`XWq^e$j)j4fks^tPeo<2c&-_6;Hbu$<?P5!lxj"
"x}m(ruGI8}N>J_{l%?!(yFigmx)&-$K0K!>k>4xxPqI{X+^#%M9+9*igAO*VHSbUBI2vL{rtE0U;lm9+Cd=!$-^%5%9Oio4j8dVIl?*B!4%LY!PVGSMFGVEt"
"EhzxH8pyo5)MxWi6esEmKY^NLy}PaY>34&dJU^$CGT6U#5g}(26(%5aQ<-X1lDIEDAy0uF#y@{sVP5Qs)1D*BS~5i$3s5RPSIQ_js_HKo|0WkrM=Eh?0M0!g"
"S@FkKddFUq%vZZfc=a6NCdTV1ELyF}_7h~6Tn=)>vi_cGcKTBQ1T5!9l^EGrX*&Innv<A)kkd}})7bq@rg0%YnL<~uy<cwh%-T*-=Qzd!WlKbh6G6hB1q*|K"
"^Zk2wAYBmIyAP347ie`AFdIV+UEyPVWB3y^`Z&UGvcmq$gK^@bLxhOfWDwo$VU&6@-bvzFG8F_&YbVo`m>30*-E#U$6~ipU<t9zsTQnhAJl$|cv^+s3G9&n&"
">-Md)-xgb|+)fnpzQMHknQAv^_IsE4*8zQCpN<b;&K04(pg!>HeIV@Cl`&a@*X2K%5z3hoI$y*G9-ronBzP48NksPxm}v7QygiI(M?(_c<Stw5y_IUKm9$el"
"y~xq&5mBuIOs^m?Kp>esYGB{!b@Ry3eCBaJk{)um83t&`nyaWKKs|nbw?;Kdrs1Y$=C+2-o=&@&G(EqYrFyy@OeXUdUrx(|5F9v{$b*pEgDh8w(8KH3vPB0l"
"C*@9et}P_h=?YQ7*eA%EUk^!InA7X;d<D#rYo9jG-lh*6xafzMIvU|~9s@X@rzCq4TTNXYXD3=t6BZzj!i|WpPCV~GKt;{ob5dOf5w^eihFo+FM!Ud+(7P0v"
"(xCAK$F&KP;QOsJxV#-^c*+i5>DS3O++9d+%Wi3u;Iqj(4>wn2!0*;b(%8<>O?+Ya(P&gm)ewMnFToA&i()>tH`nfMr!|a8@5+qFmyWe}X%Ee~uT`>!OH6Bc"
"$Hkf#0s#)c!zeD*&M$oSwx=iS5zkp#%Pmu0#z@L(0NUJG5!SDRI_xekpQ75>gVnd>$V%nP&5G$Gr(?W@BaxRNHn9dhjpk=3bLQ5~ed}w*hR9POg<J_Ke($b~"
"s1lf-mS`d?><rnP3jJ7QxM_|DQxe>TC$w*u_V{MLF#FIwBb&vvmull-!y-)J;Sv(4>*9pd%`s-yP;blhQ6`u8u;GG3u}hlAamOGOMXh(4L3}G?JF#|RSksMX"
"Wg=2?C2`>Kgfe()M8aYLWkRC@N&fYWj!-m(D5)HtXus0MHLq_02OK@>7n*dI?9eM9uP9I%e`@k@;taPFEn3TgFV2x1d3-HtDK`N?El#`hTUAibUyS2n7;4jx"
"$XBF_f-)0kPtuu>6|hSsWq&8BUI=MC&?!l@3ASl+90$kgQRz}T0<d1wof7kE1OW2(eO<)PvL?0)P8g{1Hvme&P?}Jz-L<$Ipz<8<N8{h6@F=R94~5m&vg+Ac"
"Rk@ZtSAx>Ev@V*j+6gQF6KDC}fke3Iv?d92I{`G3JoOCHLtDc+rqD6|6?}bD_yeGhO(yE=X~=`$tobF&G7Z<?Fe$jgj}wxu5{E0V(;*VajAeh24C~?PsE7H9"
"r#hi(7#@%icD&^Ko1Csq&$w6W0)HA)nc|RiO!(Acybu0z)PKW?d=&GsSVCbUuo9pz7&6#=grgo&wo`*q07%r_v7?mJ0Bl-v!>=XZ8JP&S%1RcqDL1PG+UUaz"
"S-)x70KwBaKvSt^<R5*wW{@^W_;X4+*8|7Y%`~Ch9N1#woV(+lNEP|+lnPh~O--8>II*ccGV9C0C_HB(obh}?H>2U+c139C160TA(ByX(oy$P)zkVz>rceY5"
"r`#NX;AP=R6d-u2=T6%D`1$9rJT6FL(fH=qEf_<MTTz#F>@fl}8cfNwnpI=K=ebPNR4Sd!B3q|?19G0ZkT>6}M4*0f`=1L~K7l-Po!r(SkSRFSo$LKV7v`Ty"
"-UrbVW+qf%!ejMW60vj@f7-XTq1yR~_uL6@_5lu!P@8tK^uhPv+4*9)K5r-_xR@-b=NO+_gT!(Qd67>3=<Aqa^~Fmz$gU6$F560%+{EEMYtR?;3v0Y8KOAh}"
"wuTdx6hy%ipA5m$@vk2(*bEY7Gw%loXD#hv`+C|(W3Pj5R)Jni%G9#}B)0?)4^+m8e?K6DvNcpwjvSe4_yO&@L|YrgnWz1lp;4OMH}-}AWwd7CR$XUi*bENm"
"02vHV@hQH_=vy0ZE0#mEYA6pmLJAB}{Xw7)uKBYU{ZZ2zk#kC`pQpUrhk~LTOBe|dQTwWO2*HZyyPv@FB`DuDTr@Lc>ZgXQ{zzG(LqS#(&-CA6yTl2CImQ^3"
"R@Yq9dy0;8c@a4&Mhyh^@gEG<`{0ht4-`Iix~amF$CIK2<;{uGCw`CUxwW9a6E1(+HV|{m{M~%Mzb~Ha`CGpHDD`r&Rhg99;<U?~gEPC0jc3PSo@%If=sCHb"
"u4o0^1&9!hL5gqL?o|f!bgzolA2UFHT`Wxa2Q#d8f7@tfFT|nN7U#+Sqj1Qa2P8cou;aP9C+yuMj8V(vpPxU!h**a6j%NTq4X#tMUiRzJ0C+P^7#;%NmlbgV"
"`;gj%=rp#TYndO6sEBkqaXGUJQ_V>haZ#tq0t)YQ=j0n{HgFLIC!_Cac&cg7AeTD}G1*5HIY~}OEuAx3{XUasIe(XDfJzFJdS>9*34Ef)(L>NAi}I>im&*nx"
"R^*aujS{`rHey;+X74?Cmhc%oW?`%{o&LXa6=jQ9wIZmx45kNm(nC_)FiBMUUAVy;`(|kgd;g@JpV$4;R_}3zVR#K`$Bt<8_m#$!&4Z0?X2s$ZeH=_$bx+(x"
"|ICvV5Vyd{QYPW30D(m~s`b{gcBEEC>BWdjDyOu`ko2^sq*LhK^|&z^!SM;T_=%!m2v`9TsYlLW{_-zwLzFmm71X`2CcMIMGB6m9d3wbmsoUR`l3VMfDzi&Z"
"btQDUsEEvttu|lX8kfm&V_P3}K{{2E-b9KeYLv+7_>|saT65Ffa<|{(DNQQI|HqunZF<}2TS5qPzudUZ0r6DGfz`N2C3Jbu#hpiRcfY|4WT)BgBSK}44a->!"
"b2y!J@x+X-c}6raT_M~iRCvO+HUYU7K9z^>zNGY{ri>TjLKhC<8dc_-*SRF?bD*mIgim<w(WlJIk{~sqTx0iENed|N8c?)ZUmPM*-(H-)az5bA>YVeBDI6zm"
"TUUDy<nwtlI!O^E%62J^EG^2JIWHa|)+<%!GAnYQ?Z|}WE;b*=+Zt#N?pw4l9V6Fnx=QwbE910Avg&g&#Lw4PwZQHlg~xE};bV>;$&+D^OrVF_C4UwOrYi<2"
"?gi8XfqS6a|EA?vJ4g!qd_7!R42lL_dTEVdun>Dr>f2=xiQv07RNMp{B5vTj>u}wd6KKK&JKBKRgoK*HfxEUe)i{mGye}jvr*X@f^p*dIV1hqxvCsEt3NoHt"
"Ghs1^hew=XZMe^`35JUDNu$>qm?X7zL&bXo=6?sGZ=5Ft5V?qBF|0I&C;=68OHc$#3dRRU$H1>b16&_F7gTdO?|~A!ioOf`1T7-nqX#s2J|?BIB48Sm)#m|_"
"z)iG@%ZD|}7pD3~>cM=@ai3Y`ORGI`{@{h)Lp1KiRP^ID>Q<3%it4(7SYB?JppM>AQuNU9#hnHIVil%~nV#$E1BrW^sMd*ZJ4g?=d&~8uZnq7wGkh&9HNX7j"
"dSn2p(lp4eTomeb)l+5|688gc;w-8jo>FjV<k{)nuFqBQv=AuHoAjkoS1Kq8!B$M=`)9EAEe+CLhA{}*>clm>SS5sjuSDUBZ1xv*1lfdGt%))p3C{gTaSY8j"
"zM(ZxeD_|vALXn#hoKg@pV`H$i6>~1rc0d<akVg<fS%B{VuELgB5muxzz(vELNHZ|)G56StpSsNK~zRZbV3J3f(p+1=b!3HQ-rwL{Io<>R%2W^5_A|D=A3Ph"
"=Lb@g*cWslqw_ZyG+X=kB4R-@ea)2)+zT^z1I{QN@g$B%doi3tPTa`0c0ip@ngzBKndCt*#T$At1$Sn`^E`nbkcWP5@r&St)4>#RPhm9}X{DisNC`CMFob4C"
"I`LUAaj&KHG0nF_w1Msyn-y&M>)$YY$gQJJj9(+|#zz$VyjjJ8;2Als1#kqx%eK0afNv-8loHW6+$AhcV`y$OwRiqRF-bzVV#9B}es-5qC&B=+A6iZ~8yF2H"
">b}NB)7vF}OT_AO?I+qhqnf+?%DG(lla91?k#6@li=U<*Kp1)wNJl&t+3w>44`*BIwY5|b7*064p4Os1q)(rY$Pz^OJ(Fl_!i`p)e54IywbPHhmwR*7W5vVB"
"`i=fttn52l6v_^bZwuHB7MIy;QzYHPvgT?pFSF-MK{MrevZWGp+(6z!9omz2UH;(=15C)Y9@zR*;RtE(08J;bFXMY9U*&r_0bWC{NQvP59xrdDIzy~gb^>~1"
"Kq1sOAMo6Bq(LoR-a%{PCli0h%71YB9z3gY96@cB73zvZkM_#BF(%%2uMkQK*NnQ^=^6(})5H{FDS6NaFtPAN0o?nMhU@_!vfjzIybyQ^x#@P%^Ak>g(sMkI"
"gz1S7C5(1YAaoq9SV7>Q`PVJjgNpZQq=v()Hq4i0)3YbM(%!bQT(4%W??C!2ZX)3ysi|baU~iaurvzcmTSaUuT?-!!b<=1NM-loC5EvB<Gou8d^;kQzVW^~i"
"$3HBnBDS*$v!DgFC{CG%G1$PkAmCqy=fsYl#gp}(@(ONN;1cDVPlfq%r1+piygG6;T@H!IVe0EntkZ-ooKcFwNey~2>qYERd!5Pbq(mOjXXaJkU(92a@A3dQ"
"%dGzaA}47TRM3GQe=q#%(<+^i?|#~W@gRseSP4z#V#yg}0kt%*6KV!ynh@8YHmT#s58#BrK1fnBe?u89(IvgpPcvLEH4QYZbyI888YK@f$2qn+Hvt%=0X6MO"
"F{7&O66pyKzp;qT@tymKRQq_Ej8diUUvya8I3nZf0Ha>O-jSi8@=!o`?xb8|%wpsY)CF)sJ;pQKF5Ww0Rl3ACHgDVF;zhnNZpjDh2^h14v~S1>iii6Uc(*X>"
"XNU=Fko>!<sKP`jjYK&I55nMBX1eD)eqkv64aiEl&GQ@ap6h4W{M)JU6(@!+7hg#+IaY%AA0Oi6cSkvQu&7Wp#L>qFQk5)x!{6!Dq!kEL1l$q~HyVyh%M=M!"
"Ed`PRgzuk(riwHtAd|EgoyuyPm6T~vLs_e)r>{`|p)@o!Y-pwB(+%>_ybT)>G9x?>Sjq|{{>RrnzX8r&bR^zfgoQ>14QLbkwvM9@(e91JVh(i}N{qy$)PgJA"
"h97?Diy1$HoWDEy+=r;TL2*XiEM?#?M)sS-=?~o|O8?ORh$K!kp{GYY8fsyWe!YxMmhu@MDlvt_X_ILaSKAF?WlQ{Z>wDg*MmVkt3c*i0P{m+G!8n~)Yx|DK"
"yM0C_r(0G;oVQS6!??t+c-*MKPgfaONe`zVjyYF^Ok14Wwb2fbo(*MXDm11aYs^UqOqYL;Fb0wE#eO~op+J3U`TXY9bQ?q(FyZH79IZ!Gq_Z%NNgjMJ^B+@q"
"3f0nggPHGhUpT+iVZ`=%B*8I!Lyzp0aZ}2KIgli2w-0_{rcAI7t4%EBwMg%M8Sn6g#;#^H3e`k+_qM%_b@KNbjDBrA%QV@4lMe$rwnufY<0oI6Y^YzeeMt>X"
"L^cxx%|{KQPfW<-)cFF&_PD12^5+N@%KBYZ5Mh%`iKZV=OTYym5f%~zNt9pjt<<fgmPE&p*_c{rR0JFI0b@Kv1d}4|wD6`SExkLO3Krt9!v5Xs?7^OfhV!`l"
">pjs-6kqAm`=?L#u<aOGZN-tSzPB&5SPQJ#Tls$UoAl7Ve)WXpihi>eO5Nu>+?EyPf&<)6V^mE1Acz(F;JvD9Ive`t_!;s1ST^wL%|Wr?D37iJQkBe+MW%T("
"!*ObMa`D0(^csFAve1O+D5P$HH}W1ifqBIV9`Q#ySxeni?2nTwHO^)b&3^`ym4p*54qmr^Qeg%^87+a#e=s4|KS(kKhO32Qkap^ul85+Y`Z7yCnNtX?vga6T"
"*u}&sJ@t0h`z-*~#=tkq9vS9w6F5_M8XmD-z$b(9D=RXfDliitfu#B3fMDcns~g120mvc~!*77Xz^emVedhb;lp*J(EK%E26^5}D&}JJNNh%ZbOyNYu7=k0N"
"qeCo~9*us-xf*FQ1HQ`a4U#DYm1hH;ex79caE*<;rA8DY)5$pb%kZAsgFpRugnJiAqWn8_nGR~Qm6l9sfYyB7_I2{Qi#=SwgY-oWXRRwP)w6%hj&SJKM@*{f"
"KpI{y#+sFu^BUlP^Q3I}wZ$JmTic{}K<2#sAdgyb2ealk&zVlttb}%hPp$S@S1NJe4}!B-?zTc4iIBcC8MZw8a!E2_r`JaKhWYX2k*aV}lx#YWAU2pci4c#U"
"aQASt{uTb!bIiDqnjiUoldrfCcW;OeUe>-E(|w%-n(6yTyG<1hY!a#PmA`UEc;i~9m+eIEJavs9Sssccj}(3SdoOA|{yDOplFQ7(P4;^RHCsxI(t(v6M~Uy="
"jAUEw$`x;o-{8GgUe4o%Xjlk({!=&He(&yaI6Q$G8wiMc&2<;KS#aNFx+$f(%_r~nr45fV=*D3757mes>ExmBE+{QF;*JW<Tv7Km`GmLx!fx2b8XVHRHB#EB"
"tP@iZj|L<TEB4J8uU1Prs&U2{2}On?qZ;=Vfoqm*xNVFmTa|aLBvGe7z0EA7SYdnKQ0bnq*`vg$7+D)aq4inBm!F+QtT7V~mOoxwZ1dI380~y5i<nd>2D;p}"
"EY1nG1LH%z<JZQ{EXwwW(g;EN|4}NJAh-O&ff3?eF&3ZiQ+@1csppO8s18JcosjzmN-zpnZ5W+65w;ui)p&^zMUQkr#)cOYu<P3(SaXCq(-hE-6GK`Dk0wrP"
"vDZwdfc&~uB|tP<4y`)V@##l1y_?JWZ}f-3L_~{zWJFiaIKf;PNn~6vIdmBjyPNBB#}|!PvdD+&B6od6T=@-PxnSYBbVQGz1l<!PHD^edSSbY@@wCGeUqq#?"
"^`oZ1O-Kl9Ady$xl1Kj5{xha6$7$|0MaR9juT8(hV%LnV3HJ4oq9If1e`ZnM4lIYCTw5g5((t<`$Wnr%a_+Yj0nkETm>*D@{4VbwBs;Z#=NIafTOW5(3sr7d"
";n($ubN~PVdIQEUzC7g^00E+>0q(8=fE>jMvBYQl0ssI200dcD"
)


# ================= UNIVERSAL MOVIEPY 1.x / 2.x HELPERS =================
def clip_set_duration(clip, duration: float):
    return clip.with_duration(duration) if hasattr(clip, "with_duration") else clip.set_duration(duration)


def clip_set_pos(clip, pos):
    return clip.with_position(pos) if hasattr(clip, "with_position") else clip.set_pos(pos)


def clip_set_audio(clip, audio_clip):
    return clip.with_audio(audio_clip) if hasattr(clip, "with_audio") else clip.set_audio(audio_clip)


def clip_subclip(clip, t_start: float, t_end: float):
    return clip.subclipped(t_start, t_end) if hasattr(clip, "subclipped") else clip.subclip(t_start, t_end)


def clip_crop(clip, x1: float, y1: float, x2: float, y2: float):
    x1, y1, x2, y2 = int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))
    if hasattr(clip, "cropped"):
        return clip.cropped(x1=x1, y1=y1, x2=x2, y2=y2)
    return clip.crop(x1=x1, y1=y1, x2=x2, y2=y2)


def clip_resize(clip, newsize=None, width=None, height=None):
    if hasattr(clip, "resized"):
        return clip.resized(new_size=newsize, width=width, height=height)
    return clip.resize(newsize=newsize, width=width, height=height)


def clip_time_mirror(clip):
    if hasattr(clip, "with_effects") and hasattr(vfx, "TimeMirror"):
        return clip.with_effects([vfx.TimeMirror()])
    return clip.fx(vfx.time_mirror)


def clip_loop(clip, duration: float):
    if hasattr(clip, "with_effects") and hasattr(vfx, "Loop"):
        return clip.with_effects([vfx.Loop(duration=duration)])
    return clip.loop(duration=duration)
# ========================================================================


def get_safe_font(size: int = 28):
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "arialbd.ttf",
        "arial.ttf"
    ]
    for path in font_candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def ascii_safe(text: str) -> str:
    """Removes emojis and non-ASCII characters so PIL ImageDraw never throws latin-1 error."""
    return text.encode("ascii", errors="ignore").decode("ascii").strip()


def ensure_studio_anchor_video(anchor_video_path=None) -> Path:
    """
    Locates the live moving studio anchor video from:
    1. Explicit path or repo root / assets folder (anchor_studio.mp4 or 1000121747.mp4)
    2. Built-in EMBEDDED_ANCHOR_B85 payload (auto-extracted to assets/anchor_studio.mp4)
    """
    candidates = []
    if anchor_video_path:
        candidates.append(Path(anchor_video_path))

    candidates.extend([
        Path("anchor_studio.mp4"),
        ASSETS_DIR / "anchor_studio.mp4",
        Path("1000121747.mp4"),
        ASSETS_DIR / "1000121747.mp4",
        Path("user_uploaded_files/ttl=63d/user_uploaded/1000121747.mp4"),
    ])

    for folder in [Path("."), ASSETS_DIR]:
        if folder.exists() and folder.is_dir():
            for mp4 in sorted(folder.glob("*.mp4")):
                if not mp4.name.startswith(("Short_", "Long_", "final_", "temp_", "test_")) and mp4 not in candidates:
                    candidates.append(mp4)

    for cand in candidates:
        try:
            if cand.exists() and cand.is_file() and cand.stat().st_size > 15000:
                logging.info(f"✓ Found studio anchor video: {cand} ({cand.stat().st_size // 1024} KB)")
                return cand
        except Exception:
            continue

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    extracted_path = ASSETS_DIR / "anchor_studio.mp4"
    try:
        raw_bytes = lzma.decompress(base64.b85decode(EMBEDDED_ANCHOR_B85))
        extracted_path.write_bytes(raw_bytes)
        logging.info(f"✓ Unpacked built-in studio anchor video to {extracted_path} ({len(raw_bytes) // 1024} KB)")
        return extracted_path
    except Exception as e:
        logging.error(f"Failed to unpack embedded anchor video: {e}")
        return extracted_path


def apply_ken_burns_motion(img_path: Path, duration: float, target_w: int, target_h: int, zoom_in: bool = True):
    """
    Applies smooth 30fps Ken Burns cinematic zoom & gentle pan to a static scene image
    so top-screen B-roll visuals flow dynamically instead of looking frozen.
    """
    base_img = Image.open(str(img_path)).convert("RGB")
    scale_pad = 1.18
    buf_w = int(target_w * scale_pad)
    buf_h = int(target_h * scale_pad)

    img_ratio = base_img.width / max(1, base_img.height)
    target_ratio = buf_w / max(1, buf_h)
    if img_ratio > target_ratio:
        new_h = buf_h
        new_w = int(buf_h * img_ratio)
    else:
        new_w = buf_w
        new_h = int(buf_w / max(0.01, img_ratio))

    resized_pil = base_img.resize((new_w, new_h), RESAMPLE_FILTER)
    x_off = (new_w - buf_w) // 2
    y_off = (new_h - buf_h) // 2
    master_pil = resized_pil.crop((x_off, y_off, x_off + buf_w, y_off + buf_h))
    dur = max(0.5, float(duration))

    def make_frame(t):
        progress = min(1.0, max(0.0, t / dur))
        smooth_p = 0.5 - 0.5 * math.cos(math.pi * progress)
        if not zoom_in:
            smooth_p = 1.0 - smooth_p

        cur_scale = 1.0 + 0.14 * smooth_p
        crop_w = int(buf_w / cur_scale)
        crop_h = int(buf_h / cur_scale)

        max_dx = max(0, buf_w - crop_w)
        max_dy = max(0, buf_h - crop_h)
        cx = int(max_dx * (0.35 + 0.30 * smooth_p))
        cy = int(max_dy * 0.50)

        frame_pil = master_pil.crop((cx, cy, cx + crop_w, cy + crop_h)).resize((target_w, target_h), Image.BILINEAR)
        return np.asarray(frame_pil)

    clip = VideoClip(make_frame, duration=dur)
    clip.size = (target_w, target_h)
    return clip


def prepare_flowing_anchor_clip(anchor_path: Path, total_duration: float, target_w: int, target_h: int):
    raw_clip = VideoFileClip(str(anchor_path)).without_audio()

    if raw_clip.w >= 2000 and raw_clip.h >= 1000 and raw_clip.duration > 12.0:
        start_t = 2.65
        end_t = min(raw_clip.duration - 0.15, 25.40)
        work_clip = clip_subclip(raw_clip, start_t, end_t)
        work_clip = clip_crop(work_clip, x1=880, y1=0, x2=1843, y2=856)
    elif raw_clip.w >= 1800 and raw_clip.h >= 1000 and raw_clip.duration > 12.0:
        start_t = 2.65 if raw_clip.duration > 20.0 else 0.0
        end_t = min(raw_clip.duration - 0.15, 25.40)
        work_clip = clip_subclip(raw_clip, start_t, end_t)
        crop_h = min(raw_clip.h, 856)
        crop_w = int(crop_h * (target_w / max(1, target_h)))
        x_center = int(raw_clip.w * 0.56)
        x1 = max(0, x_center - crop_w // 2)
        work_clip = clip_crop(work_clip, x1=x1, y1=0, x2=x1 + crop_w, y2=crop_h)
    else:
        work_clip = raw_clip

    clip_ratio = work_clip.w / max(1, work_clip.h)
    target_ratio = target_w / max(1, target_h)
    if abs(clip_ratio - target_ratio) < 0.03:
        sized_clip = clip_resize(work_clip, newsize=(target_w, target_h))
    elif clip_ratio > target_ratio:
        sized_clip = clip_resize(work_clip, height=target_h)
        dx = (sized_clip.w - target_w) / 2
        sized_clip = clip_crop(sized_clip, x1=dx, y1=0, x2=dx + target_w, y2=target_h)
    else:
        sized_clip = clip_resize(work_clip, width=target_w)
        dy = (sized_clip.h - target_h) / 2
        sized_clip = clip_crop(sized_clip, x1=0, y1=dy, x2=target_w, y2=dy + target_h)

    if sized_clip.duration < total_duration:
        try:
            rev_clip = clip_time_mirror(sized_clip)
            ping_pong = concatenate_videoclips([sized_clip, rev_clip], method="compose")
            repeats = int(math.ceil(total_duration / max(0.5, ping_pong.duration))) + 1
            looped = clip_subclip(concatenate_videoclips([ping_pong] * repeats, method="compose"), 0, total_duration)
            return looped, [raw_clip, work_clip, sized_clip, rev_clip, ping_pong]
        except Exception:
            looped = clip_loop(sized_clip, duration=total_duration)
            return looped, [raw_clip, work_clip, sized_clip]
    else:
        trimmed = clip_subclip(sized_clip, 0, total_duration)
        return trimmed, [raw_clip, work_clip, sized_clip]


def create_breaking_news_banner(width: int, height: int, title_text: str, is_breaking: bool = False) -> str:
    banner_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(banner_img)
    font = get_safe_font(28)

    tag_w = 275
    tag_bg = (220, 16, 42, 255) if is_breaking else (195, 12, 28, 255)
    draw.rectangle([0, 0, tag_w, height], fill=tag_bg)

    dot_r = 9
    dot_x = 28
    dot_y = height // 2
    draw.ellipse([dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r], fill=(255, 255, 255))

    label_text = "BREAKING" if is_breaking else "TOP NEWS"
    draw.text((dot_x + 20, height // 2 - 16), label_text, fill=(255, 255, 255), font=font)

    draw.rectangle([tag_w, 0, width, height], fill=(10, 18, 34, 245))
    draw.line([(0, 0), (width, 0)], fill=(255, 255, 255, 180), width=3)
    draw.line([(0, height - 3), (width, height - 3)], fill=(220, 16, 42, 255), width=3)

    clean_title = ascii_safe(title_text.replace("#Shorts", "").replace("#shorts", ""))
    if not clean_title:
        clean_title = "LATEST BREAKING HEADLINE UPDATE"
    if len(clean_title) > 40:
        clean_title = clean_title[:37] + "..."
    draw.text((tag_w + 24, height // 2 - 16), clean_title, fill=(255, 255, 255), font=font)

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    temp_banner_path = ASSETS_DIR / "temp_banner.png"
    banner_img.save(temp_banner_path, "PNG")
    return str(temp_banner_path)


def create_studio_lower_third(width: int, height: int = 86) -> str:
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    badge_w = 560
    badge_h = 68
    x0 = (width - badge_w) // 2
    y0 = (height - badge_h) // 2

    try:
        draw.rounded_rectangle([x0, y0, x0 + badge_w, y0 + badge_h], radius=14, fill=(198, 22, 32, 245), outline=(255, 255, 255, 210), width=2)
    except Exception:
        draw.rectangle([x0, y0, x0 + badge_w, y0 + badge_h], fill=(198, 22, 32, 245))

    font = get_safe_font(42)
    text = "BREAKING NEWS"
    draw.text((x0 + 92, y0 + 11), text, fill=(255, 255, 255, 255), font=font)

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ASSETS_DIR / "temp_lower_third.png"
    img.save(out_path, "PNG")
    return str(out_path)


def create_split_screen_video(scene_data_list, output_path, video_title="NEWS UPDATE", is_breaking=False, anchor_video_path=None):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    all_allocated_clips = []

    try:
        top_height = SHORT_HEIGHT // 2
        bottom_height = SHORT_HEIGHT - top_height

        top_clips = []
        audio_clips = []

        for idx, item in enumerate(scene_data_list):
            img_path = Path(item["image_path"])
            aud_path = Path(item["audio_path"])

            s_audio = AudioFileClip(str(aud_path))
            scene_duration = s_audio.duration
            audio_clips.append(s_audio)
            all_allocated_clips.append(s_audio)

            img_clip = apply_ken_burns_motion(
                img_path=img_path,
                duration=scene_duration,
                target_w=SHORT_WIDTH,
                target_h=top_height,
                zoom_in=(idx % 2 == 0)
            )
            top_clips.append(img_clip)
            all_allocated_clips.append(img_clip)

        final_audio = concatenate_audioclips(audio_clips)
        top_final = concatenate_videoclips(top_clips, method="compose")
        total_duration = final_audio.duration
        all_allocated_clips.extend([final_audio, top_final])

        resolved_anchor_path = ensure_studio_anchor_video(anchor_video_path)
        bottom_clip, extra_clips = prepare_flowing_anchor_clip(
            anchor_path=resolved_anchor_path,
            total_duration=total_duration,
            target_w=SHORT_WIDTH,
            target_h=bottom_height
        )
        all_allocated_clips.extend(extra_clips)
        all_allocated_clips.append(bottom_clip)

        split_layout = clips_array([[top_final], [bottom_clip]])
        all_allocated_clips.append(split_layout)

        banner_h = 90
        banner_file = create_breaking_news_banner(SHORT_WIDTH, banner_h, video_title, is_breaking)
        banner_clip = clip_set_pos(clip_set_duration(ImageClip(banner_file), total_duration), (0, top_height - (banner_h // 2)))
        all_allocated_clips.append(banner_clip)

        lower_h = 86
        lower_file = create_studio_lower_third(SHORT_WIDTH, lower_h)
        lower_clip = clip_set_pos(clip_set_duration(ImageClip(lower_file), total_duration), (0, SHORT_HEIGHT - lower_h - 32))
        all_allocated_clips.append(lower_clip)

        final_composite = CompositeVideoClip(
            [split_layout, banner_clip, lower_clip],
            size=(SHORT_WIDTH, SHORT_HEIGHT)
        )
        final_video = clip_set_audio(final_composite, final_audio)
        all_allocated_clips.extend([final_composite, final_video])

        final_video.write_videofile(
            str(output_path),
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            bitrate="6000k",
            preset="ultrafast",
            threads=4,
            logger=None
        )

        logging.info(f"✓ Split-Screen Short with Flowing Anchor ready: {output_path.name}")
        return output_path

    finally:
        for c in all_allocated_clips:
            try:
                c.close()
            except Exception:
                pass


def create_long_video(scene_data_list, output_path, video_title="SPECIAL REPORT", anchor_video_path=None):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    all_allocated_clips = []

    try:
        video_clips = []
        audio_clips = []
        resolved_anchor_path = ensure_studio_anchor_video(anchor_video_path)

        for idx, item in enumerate(scene_data_list):
            img_path = Path(item["image_path"])
            aud_path = Path(item["audio_path"])

            s_audio = AudioFileClip(str(aud_path))
            scene_duration = s_audio.duration
            audio_clips.append(s_audio)
            all_allocated_clips.append(s_audio)

            broll_clip = apply_ken_burns_motion(
                img_path=img_path,
                duration=scene_duration,
                target_w=LONG_WIDTH,
                target_h=LONG_HEIGHT,
                zoom_in=(idx % 2 == 0)
            )
            all_allocated_clips.append(broll_clip)

            try:
                pip_w, pip_h = 460, 410
                anchor_pip, extra = prepare_flowing_anchor_clip(
                    anchor_path=resolved_anchor_path,
                    total_duration=scene_duration,
                    target_w=pip_w,
                    target_h=pip_h
                )
                all_allocated_clips.extend(extra)
                anchor_pip = clip_set_pos(anchor_pip, (LONG_WIDTH - pip_w - 40, LONG_HEIGHT - pip_h - 140))
                scene_comp = clip_set_duration(CompositeVideoClip([broll_clip, anchor_pip], size=(LONG_WIDTH, LONG_HEIGHT)), scene_duration)
                video_clips.append(scene_comp)
                all_allocated_clips.extend([anchor_pip, scene_comp])
            except Exception:
                video_clips.append(broll_clip)

        final_audio = concatenate_audioclips(audio_clips)
        final_visual = concatenate_videoclips(video_clips, method="compose")
        total_duration = final_audio.duration
        all_allocated_clips.extend([final_audio, final_visual])

        banner_h = 84
        banner_file = create_breaking_news_banner(LONG_WIDTH, banner_h, video_title, is_breaking=False)
        banner_clip = clip_set_pos(clip_set_duration(ImageClip(banner_file), total_duration), (0, LONG_HEIGHT - banner_h - 36))
        all_allocated_clips.append(banner_clip)

        final_video = clip_set_audio(CompositeVideoClip([final_visual, banner_clip], size=(LONG_WIDTH, LONG_HEIGHT)), final_audio)
        all_allocated_clips.append(final_video)

        final_video.write_videofile(
            str(output_path),
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            bitrate="8000k",
            preset="ultrafast",
            threads=4,
            logger=None
        )

        logging.info(f"✓ Long Video ready: {output_path.name}")
        return output_path

    finally:
        for c in all_allocated_clips:
            try:
                c.close()
            except Exception:
                pass
