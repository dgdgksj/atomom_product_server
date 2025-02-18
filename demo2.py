# -*- coding: utf-8 -*-
import copy
import string
import argparse

import torch
import torch.backends.cudnn as cudnn
import torch.utils.data
import torch.nn.functional as F

from utils import CTCLabelConverter, AttnLabelConverter
from dataset import RawDataset, AlignCollate
from model import Model
from craftPytorch import cDemo
from PIL import ImageFont, ImageDraw, Image
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
import cv2
import numpy as np
import shutil
import time
import videomaker
def setModel(opt):
    start=time.time()
    """ model configuration """
    if 'CTC' in opt.Prediction:
        converter = CTCLabelConverter(opt.character)
    else:
        converter = AttnLabelConverter(opt.character)
    opt.num_class = len(converter.character)

    if opt.rgb:
        opt.input_channel = 3
    model = Model(opt)
    # print('model input parameters', opt.imgH, opt.imgW, opt.num_fiducial, opt.input_channel, opt.output_channel,
    #       opt.hidden_size, opt.num_class, opt.batch_max_length, opt.Transformation, opt.FeatureExtraction,
    #       opt.SequenceModeling, opt.Prediction)
    model = torch.nn.DataParallel(model).to(device)

    # load model
    # print('loading pretrained model from %s' % opt.saved_model)
    print("text recognition model load",time.time()-start)
    model.load_state_dict(torch.load(opt.saved_model, map_location=device))
    return (model,converter)



def demo(opt,model):
    model,converter=model
    # prepare data. two demo images from https://github.com/bgshih/crnn#run-demo
    AlignCollate_demo = AlignCollate(imgH=opt.imgH, imgW=opt.imgW, keep_ratio_with_pad=opt.PAD)
    demo_data = RawDataset(root=opt.image_folder, opt=opt)  # use RawDataset

    demo_loader = torch.utils.data.DataLoader(
        demo_data, batch_size=opt.batch_size,
        shuffle=False,
        # num_workers=int(opt.workers),
        num_workers=int(0),
        collate_fn=AlignCollate_demo, pin_memory=True)
    # print(demo_loader)
    # predict
    model.eval()
    cnt=0
    texts=[]
    with torch.no_grad():
        for image_tensors, image_path_list in demo_loader:
            # print(cnt)
            # craftTest(demo_data.__getitem__(cnt)[1])
            # cnt+=1
            # print(image_path_list)

            batch_size = image_tensors.size(0)
            image = image_tensors.to(device)

            # For max length prediction
            length_for_pred = torch.IntTensor([opt.batch_max_length] * batch_size).to(device)
            text_for_pred = torch.LongTensor(batch_size, opt.batch_max_length + 1).fill_(0).to(device)

            if 'CTC' in opt.Prediction:
                # print(image)
                # print(type(model))
                preds = model(image, text_for_pred)
                # print("여기1")
                # Select max probabilty (greedy decoding) then decode index to character
                preds_size = torch.IntTensor([preds.size(1)] * batch_size)
                _, preds_index = preds.max(2)
                # preds_index = preds_index.view(-1)
                preds_str = converter.decode(preds_index, preds_size)

            else:
                preds = model(image, text_for_pred, is_train=False)
                # select max probabilty (greedy decoding) then decode index to character
                _, preds_index = preds.max(2)
                preds_str = converter.decode(preds_index, length_for_pred)

            # log = open(f'./log_demo_result.txt', 'a')
            dashed_line = '-' * 80
            head = f'{"image_path":25s}\t{"predicted_labels":25s}\tconfidence score'

            # print(f'{dashed_line}\n{head}\n{dashed_line}')
            # log.write(f'{dashed_line}\n{head}\n{dashed_line}\n')

            preds_prob = F.softmax(preds, dim=2)
            preds_max_prob, _ = preds_prob.max(dim=2)
            for img_name, pred, pred_max_prob in zip(image_path_list, preds_str, preds_max_prob):
                if 'Attn' in opt.Prediction:
                    pred_EOS = pred.find('[s]')
                    pred = pred[:pred_EOS]  # prune after "end of sentence" token ([s])
                    pred_max_prob = pred_max_prob[:pred_EOS]

                # calculate confidence score (= multiply of pred_max_prob)
                confidence_score = pred_max_prob.cumprod(dim=0)[-1]
                texts.append(pred)
                # print(f'{img_name:25s}\t{pred:25s}\t{confidence_score:0.4f}')
                # log.write(f'{img_name:25s}\t{pred:25s}\t{confidence_score:0.4f}\n')

            # log.close()
    # print('-' * 80)
    # print(texts)
    del texts[len(texts)-1]
    return texts
import pathlib
import os
def saveCraftResult(dirPath,imgs,img):
    cnt=0
    for i in imgs:
        savePath= os.path.join(dirPath, str(cnt)+".jpg")
        cv2.imwrite(savePath,i)
        cnt+=1
    savePath = os.path.join(dirPath, "result" + ".jpg")
    cv2.imwrite(savePath, img)

    #
    # ROOT_DIR = dirPath
    # image1 = pathlib.Path(os.path.join(ROOT_DIR))
    # image_list = list(image1.glob('*.jpg'))
    # 이건 실험 코드 175부터
def getCraftResult(imagePath,craftModel):
    imgs, img,points = cDemo.main(imagePath,craftModel)
    # print(len(imgs))
    resultImgs=[]
    cnt=0
    for i in imgs:
        rows,cols,_=i.shape
        if(rows != 0 and cols != 0):
            # print(i.shape)
            resultImgs.append(i)
            # cv2.imshow("img",i)
            # cv2.waitKey(0)
        else:
            print("len(imgs)",len(imgs),'len(points)',len(points),'cnt',cnt)
            del points[cnt]
            cnt-=1
        cnt+=1
    return resultImgs, img,points
def putText(img,points,texts):
    # print(len(points),len(texts))
    fontSize=32
    font = ImageFont.truetype('malgun.ttf', fontSize)
    img_pil = Image.fromarray(img)
    draw = ImageDraw.Draw(img_pil)
    for i in range(len(points)):
        point=points[i]
        text=texts[i]
        #draw.text((point[1],point[0]), text, font=font, fill=(0, 69, 255, 0))
        draw.text((point[1], point[0]), text, font=font, fill=(0, 215, 255, 0))
        # cv2.putText는 한글안됨
        # cv2.putText(img, text, (point[1],point[0]), cv2.FONT_HERSHEY_SIMPLEX, 5, (255, 0, 255), 5, cv2.LINE_AA)
    img = np.array(img_pil)

    return img

def craftOperation(imgPath,craftModel,dirPath):
    imgs,img,points=getCraftResult(imgPath,craftModel)
    if not (os.path.isdir(dirPath)):
        os.makedirs(os.path.join(dirPath))
    saveCraftResult(dirPath,imgs,img)
    return img,points


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--image_folder',help='path to image_folder which contains text images')

    parser.add_argument('--workers', type=int, help='number of data loading workers', default=4)
    parser.add_argument('--batch_size', type=int, default=192, help='input batch size')
    parser.add_argument('--saved_model', required=True, help="path to saved_model to evaluation")
    """ Data processing """
    parser.add_argument('--batch_max_length', type=int, default=25, help='maximum-label-length')
    parser.add_argument('--imgH', type=int, default=32, help='the height of the input image')
    parser.add_argument('--imgW', type=int, default=100, help='the width of the input image')
    parser.add_argument('--rgb', action='store_true', help='use rgb input')
    # parser.add_argument('--character', type=str,
    #                     default='0123456789abcdefghijklmnopqrstuvwxyz가각간갇갈감갑값갓강갖같갚갛개객걀걔거걱건걷걸검겁것겉게겨격겪견결겹경곁계고곡곤곧골곰곱곳공과관광괜괴굉교구국군굳굴굵굶굽궁권귀귓규균귤그극근글긁금급긋긍기긴길김깅깊까깍깎깐깔깜깝깡깥깨꺼꺾껌껍껏껑께껴꼬꼭꼴꼼꼽꽂꽃꽉꽤꾸꾼꿀꿈뀌끄끈끊끌끓끔끗끝끼낌나낙낚난날낡남납낫낭낮낯낱낳내냄냇냉냐냥너넉넌널넓넘넣네넥넷녀녁년념녕노녹논놀놈농높놓놔뇌뇨누눈눕뉘뉴늄느늑는늘늙능늦늬니닐님다닥닦단닫달닭닮담답닷당닿대댁댐댓더덕던덜덟덤덥덧덩덮데델도독돈돌돕돗동돼되된두둑둘둠둡둥뒤뒷드득든듣들듬듭듯등디딩딪따딱딴딸땀땅때땜떠떡떤떨떻떼또똑뚜뚫뚱뛰뜨뜩뜯뜰뜻띄라락란람랍랑랗래랜램랫략량러럭런럴럼럽럿렁렇레렉렌려력련렬렵령례로록론롬롭롯료루룩룹룻뤄류륙률륭르른름릇릎리릭린림립릿링마막만많말맑맘맙맛망맞맡맣매맥맨맵맺머먹먼멀멈멋멍멎메멘멩며면멸명몇모목몬몰몸몹못몽묘무묵묶문묻물뭄뭇뭐뭘뭣므미민믿밀밉밌및밑바박밖반받발밝밟밤밥방밭배백뱀뱃뱉버번벌범법벗베벤벨벼벽변별볍병볕보복볶본볼봄봇봉뵈뵙부북분불붉붐붓붕붙뷰브븐블비빌빔빗빚빛빠빡빨빵빼뺏뺨뻐뻔뻗뼈뼉뽑뿌뿐쁘쁨사삭산살삶삼삿상새색샌생샤서석섞선설섬섭섯성세섹센셈셋셔션소속손솔솜솟송솥쇄쇠쇼수숙순숟술숨숫숭숲쉬쉰쉽슈스슨슬슴습슷승시식신싣실싫심십싯싱싶싸싹싼쌀쌍쌓써썩썰썹쎄쏘쏟쑤쓰쓴쓸씀씌씨씩씬씹씻아악안앉않알앓암압앗앙앞애액앨야약얀얄얇양얕얗얘어억언얹얻얼엄업없엇엉엊엌엎에엔엘여역연열엷염엽엿영옆예옛오옥온올옮옳옷옹와완왕왜왠외왼요욕용우욱운울움웃웅워원월웨웬위윗유육율으윽은을음응의이익인일읽잃임입잇있잊잎자작잔잖잘잠잡잣장잦재쟁쟤저적전절젊점접젓정젖제젠젯져조족존졸좀좁종좋좌죄주죽준줄줌줍중쥐즈즉즌즐즘증지직진질짐집짓징짙짚짜짝짧째쨌쩌쩍쩐쩔쩜쪽쫓쭈쭉찌찍찢차착찬찮찰참찻창찾채책챔챙처척천철첩첫청체쳐초촉촌촛총촬최추축춘출춤춥춧충취츠측츰층치칙친칠침칫칭카칸칼캄캐캠커컨컬컴컵컷케켓켜코콘콜콤콩쾌쿄쿠퀴크큰클큼키킬타탁탄탈탑탓탕태택탤터턱턴털텅테텍텔템토톤톨톱통퇴투툴툼퉁튀튜트특튼튿틀틈티틱팀팅파팎판팔팝패팩팬퍼퍽페펜펴편펼평폐포폭폰표푸푹풀품풍퓨프플픔피픽필핏핑하학한할함합항해핵핸햄햇행향허헌험헤헬혀현혈협형혜호혹혼홀홈홉홍화확환활황회획횟횡효후훈훌훔훨휘휴흉흐흑흔흘흙흡흥흩희흰히힘?!',
    #                     help='character label')
    # parser.add_argument('--character', type=str,
    #                     default='가각간갇갈감갑값갓강갖같갚갛개객걀걔거걱건걷걸검겁것겉게겨격겪견결겹경곁계고곡곤곧골곰곱곳공과관광괜괴굉교구국군굳굴굵굶굽궁권귀귓규균귤그극근글긁금급긋긍기긴길김깅깊까깍깎깐깔깜깝깡깥깨꺼꺾껌껍껏껑께껴꼬꼭꼴꼼꼽꽂꽃꽉꽤꾸꾼꿀꿈뀌끄끈끊끌끓끔끗끝끼낌나낙낚난날낡남납낫낭낮낯낱낳내냄냇냉냐냥너넉넌널넓넘넣네넥넷녀녁년념녕노녹논놀놈농높놓놔뇌뇨누눈눕뉘뉴늄느늑는늘늙능늦늬니닐님다닥닦단닫달닭닮담답닷당닿대댁댐댓더덕던덜덟덤덥덧덩덮데델도독돈돌돕돗동돼되된두둑둘둠둡둥뒤뒷드득든듣들듬듭듯등디딩딪따딱딴딸땀땅때땜떠떡떤떨떻떼또똑뚜뚫뚱뛰뜨뜩뜯뜰뜻띄라락란람랍랑랗래랜램랫략량러럭런럴럼럽럿렁렇레렉렌려력련렬렵령례로록론롬롭롯료루룩룹룻뤄류륙률륭르른름릇릎리릭린림립릿링마막만많말맑맘맙맛망맞맡맣매맥맨맵맺머먹먼멀멈멋멍멎메멘멩며면멸명몇모목몬몰몸몹못몽묘무묵묶문묻물뭄뭇뭐뭘뭣므미민믿밀밉밌및밑바박밖반받발밝밟밤밥방밭배백뱀뱃뱉버번벌범법벗베벤벨벼벽변별볍병볕보복볶본볼봄봇봉뵈뵙부북분불붉붐붓붕붙뷰브븐블비빌빔빗빚빛빠빡빨빵빼뺏뺨뻐뻔뻗뼈뼉뽑뿌뿐쁘쁨사삭산살삶삼삿상새색샌생샤서석섞선설섬섭섯성세섹센셈셋셔션소속손솔솜솟송솥쇄쇠쇼수숙순숟술숨숫숭숲쉬쉰쉽슈스슨슬슴습슷승시식신싣실싫심십싯싱싶싸싹싼쌀쌍쌓써썩썰썹쎄쏘쏟쑤쓰쓴쓸씀씌씨씩씬씹씻아악안앉않알앓암압앗앙앞애액앨야약얀얄얇양얕얗얘어억언얹얻얼엄업없엇엉엊엌엎에엔엘여역연열엷염엽엿영옆예옛오옥온올옮옳옷옹와완왕왜왠외왼요욕용우욱운울움웃웅워원월웨웬위윗유육율으윽은을음응의이익인일읽잃임입잇있잊잎자작잔잖잘잠잡잣장잦재쟁쟤저적전절젊점접젓정젖제젠젯져조족존졸좀좁종좋좌죄주죽준줄줌줍중쥐즈즉즌즐즘증지직진질짐집짓징짙짚짜짝짧째쨌쩌쩍쩐쩔쩜쪽쫓쭈쭉찌찍찢차착찬찮찰참찻창찾채책챔챙처척천철첩첫청체쳐초촉촌촛총촬최추축춘출춤춥춧충취츠측츰층치칙친칠침칫칭카칸칼캄캐캠커컨컬컴컵컷케켓켜코콘콜콤콩쾌쿄쿠퀴크큰클큼키킬타탁탄탈탑탓탕태택탤터턱턴털텅테텍텔템토톤톨톱통퇴투툴툼퉁튀튜트특튼튿틀틈티틱팀팅파팎판팔팝패팩팬퍼퍽페펜펴편펼평폐포폭폰표푸푹풀품풍퓨프플픔피픽필핏핑하학한할함합항해핵핸햄햇행향허헌험헤헬혀현혈협형혜호혹혼홀홈홉홍화확환활황회획횟횡효후훈훌훔훨휘휴흉흐흑흔흘흙흡흥흩희흰히힘',
    #                     help='character label')
    # parser.add_argument('--character', type=str,
    #                     default='0123456789abcdefghijklmnopqrstuvwxyz가각간갇갈감갑값갓강갖같갚갛개객걀걔거걱건걷걸검겁것겉게겨격겪견결겹경곁계고곡곤곧골곰곱곳공과관광괜괴굉교구국군굳굴굵굶굽궁권귀귓규균귤그극근글긁금급긋긍기긴길김깅깊까깍깎깐깔깜깝깡깥깨꺼꺾껌껍껏껑께껴꼬꼭꼴꼼꼽꽂꽃꽉꽤꾸꾼꿀꿈뀌끄끈끊끌끓끔끗끝끼낌나낙낚난날낡남납낫낭낮낯낱낳내냄냇냉냐냥너넉넌널넓넘넣네넥넷녀녁년념녕노녹논놀놈농높놓놔뇌뇨누눈눕뉘뉴늄느늑는늘늙능늦늬니닐님다닥닦단닫달닭닮담답닷당닿대댁댐댓더덕던덜덟덤덥덧덩덮데델도독돈돌돕돗동돼되된두둑둘둠둡둥뒤뒷드득든듣들듬듭듯등디딩딪따딱딴딸땀땅때땜떠떡떤떨떻떼또똑뚜뚫뚱뛰뜨뜩뜯뜰뜻띄라락란람랍랑랗래랜램랫략량러럭런럴럼럽럿렁렇레렉렌려력련렬렵령례로록론롬롭롯료루룩룹룻뤄류륙률륭르른름릇릎리릭린림립릿링마막만많말맑맘맙맛망맞맡맣매맥맨맵맺머먹먼멀멈멋멍멎메멘멩며면멸명몇모목몬몰몸몹못몽묘무묵묶문묻물뭄뭇뭐뭘뭣므미민믿밀밉밌및밑바박밖반받발밝밟밤밥방밭배백뱀뱃뱉버번벌범법벗베벤벨벼벽변별볍병볕보복볶본볼봄봇봉뵈뵙부북분불붉붐붓붕붙뷰브븐블비빌빔빗빚빛빠빡빨빵빼뺏뺨뻐뻔뻗뼈뼉뽑뿌뿐쁘쁨사삭산살삶삼삿상새색샌생샤서석섞선설섬섭섯성세섹센셈셋셔션소속손솔솜솟송솥쇄쇠쇼수숙순숟술숨숫숭숲쉬쉰쉽슈스슨슬슴습슷승시식신싣실싫심십싯싱싶싸싹싼쌀쌍쌓써썩썰썹쎄쏘쏟쑤쓰쓴쓸씀씌씨씩씬씹씻아악안앉않알앓암압앗앙앞애액앨야약얀얄얇양얕얗얘어억언얹얻얼엄업없엇엉엊엌엎에엔엘여역연열엷염엽엿영옆예옛오옥온올옮옳옷옹와완왕왜왠외왼요욕용우욱운울움웃웅워원월웨웬위윗유육율으윽은을음응의이익인일읽잃임입잇있잊잎자작잔잖잘잠잡잣장잦재쟁쟤저적전절젊점접젓정젖제젠젯져조족존졸좀좁종좋좌죄주죽준줄줌줍중쥐즈즉즌즐즘증지직진질짐집짓징짙짚짜짝짧째쨌쩌쩍쩐쩔쩜쪽쫓쭈쭉찌찍찢차착찬찮찰참찻창찾채책챔챙처척천철첩첫청체쳐초촉촌촛총촬최추축춘출춤춥춧충취츠측츰층치칙친칠침칫칭카칸칼캄캐캠커컨컬컴컵컷케켓켜코콘콜콤콩쾌쿄쿠퀴크큰클큼키킬타탁탄탈탑탓탕태택탤터턱턴털텅테텍텔템토톤톨톱통퇴투툴툼퉁튀튜트특튼튿틀틈티틱팀팅파팎판팔팝패팩팬퍼퍽페펜펴편펼평폐포폭폰표푸푹풀품풍퓨프플픔피픽필핏핑하학한할함합항해핵핸햄햇행향허헌험헤헬혀현혈협형혜호혹혼홀홈홉홍화확환활황회획횟횡효후훈훌훔훨휘휴흉흐흑흔흘흙흡흥흩희흰히힘?!.\'\",',
    #                     help='character label')
    parser.add_argument('--character', type=str,
                        default='0123456789abcdefghijklmnopqrstuvwxyz가각간갇갈갉갊감갑값갓갔강갖갗같갚갛개객갠갤갬갭갯갰갱갸갹갼걀걋걍걔걘걜거걱건걷걸걺검겁것겄겅겆겉겊겋게겐겔겜겝겟겠겡겨격겪견겯결겸겹겻겼경곁계곈곌곕곗고곡곤곧골곪곬곯곰곱곳공곶과곽관괄괆괌괍괏광괘괜괠괩괬괭괴괵괸괼굄굅굇굉교굔굘굡굣구국군굳굴굵굶굻굼굽굿궁궂궈궉권궐궜궝궤궷귀귁귄귈귐귑귓규균귤그극근귿글긁금급긋긍긔기긱긴긷길긺김깁깃깅깆깊까깍깎깐깔깖깜깝깟깠깡깥깨깩깬깰깸깹깻깼깽꺄꺅꺌꺼꺽꺾껀껄껌껍껏껐껑께껙껜껨껫껭껴껸껼꼇꼈꼍꼐꼬꼭꼰꼲꼴꼼꼽꼿꽁꽂꽃꽈꽉꽐꽜꽝꽤꽥꽹꾀꾄꾈꾐꾑꾕꾜꾸꾹꾼꿀꿇꿈꿉꿋꿍꿎꿔꿜꿨꿩꿰꿱꿴꿸뀀뀁뀄뀌뀐뀔뀜뀝뀨끄끅끈끊끌끎끓끔끕끗끙끝끼끽낀낄낌낍낏낑나낙낚난낟날낡낢남납낫났낭낮낯낱낳내낵낸낼냄냅냇냈냉냐냑냔냘냠냥너넉넋넌널넒넓넘넙넛넜넝넣네넥넨넬넴넵넷넸넹녀녁년녈념녑녔녕녘녜녠노녹논놀놂놈놉놋농높놓놔놘놜놨뇌뇐뇔뇜뇝뇟뇨뇩뇬뇰뇹뇻뇽누눅눈눋눌눔눕눗눙눠눴눼뉘뉜뉠뉨뉩뉴뉵뉼늄늅늉느늑는늘늙늚늠늡늣능늦늪늬늰늴니닉닌닐닒님닙닛닝닢다닥닦단닫달닭닮닯닳담답닷닸당닺닻닿대댁댄댈댐댑댓댔댕댜더덕덖던덛덜덞덟덤덥덧덩덫덮데덱덴델뎀뎁뎃뎄뎅뎌뎐뎔뎠뎡뎨뎬도독돈돋돌돎돐돔돕돗동돛돝돠돤돨돼됐되된될됨됩됫됴두둑둔둘둠둡둣둥둬뒀뒈뒝뒤뒨뒬뒵뒷뒹듀듄듈듐듕드득든듣들듦듬듭듯등듸디딕딘딛딜딤딥딧딨딩딪따딱딴딸텭땀땁땃땄땅땋때땍땐땔땜땝땟땠땡떠떡떤떨떪떫떰떱떳떴떵떻떼떽뗀뗄뗌뗍뗏뗐뗑뗘뗬또똑똔똘똥똬똴뙈뙤뙨뚜뚝뚠뚤뚫뚬뚱뛔뛰뛴뛸뜀뜁뜅뜨뜩뜬뜯뜰뜸뜹뜻띄띈띌띔띕띠띤띨띰띱띳띵라락란랄람랍랏랐랑랒랖랗퇏래랙랜랠램랩랫랬랭랴략랸럇량러럭런럴럼럽럿렀렁렇레렉렌렐렘렙렛렝려력련렬렴렵렷렸령례롄롑롓로록론롤롬롭롯롱롸롼뢍뢨뢰뢴뢸룀룁룃룅료룐룔룝룟룡루룩룬룰룸룹룻룽뤄뤘뤠뤼뤽륀륄륌륏륑류륙륜률륨륩툩륫륭르륵른를름릅릇릉릊릍릎리릭린릴림립릿링마막만많맏말맑맒맘맙맛망맞맡맣매맥맨맬맴맵맷맸맹맺먀먁먈먕머먹먼멀멂멈멉멋멍멎멓메멕멘멜멤멥멧멨멩며멱면멸몃몄명몇몌모목몫몬몰몲몸몹못몽뫄뫈뫘뫙뫼묀묄묍묏묑묘묜묠묩묫무묵묶문묻물묽묾뭄뭅뭇뭉뭍뭏뭐뭔뭘뭡뭣뭬뮈뮌뮐뮤뮨뮬뮴뮷므믄믈믐믓미믹민믿밀밂밈밉밋밌밍및밑바박밖밗반받발밝밞밟밤밥밧방밭배백밴밸뱀뱁뱃뱄뱅뱉뱌뱍뱐뱝버벅번벋벌벎범법벗벙벚베벡벤벧벨벰벱벳벴벵벼벽변별볍볏볐병볕볘볜보복볶본볼봄봅봇봉봐봔봤봬뵀뵈뵉뵌뵐뵘뵙뵤뵨부북분붇불붉붊붐붑붓붕붙붚붜붤붰붸뷔뷕뷘뷜뷩뷰뷴뷸븀븃븅브븍븐블븜븝븟비빅빈빌빎빔빕빗빙빚빛빠빡빤빨빪빰빱빳빴빵빻빼빽뺀뺄뺌뺍뺏뺐뺑뺘뺙뺨뻐뻑뻔뻗뻘뻠뻣뻤뻥뻬뼁뼈뼉뼘뼙뼛뼜뼝뽀뽁뽄뽈뽐뽑뽕뾔뾰뿅뿌뿍뿐뿔뿜뿟뿡쀼쁑쁘쁜쁠쁨쁩삐삑삔삘삠삡삣삥사삭삯산삳살삵삶삼삽삿샀상샅새색샌샐샘샙샛샜생샤샥샨샬샴샵샷샹섀섄섈섐섕서석섞섟선섣설섦섧섬섭섯섰성섶세섹센셀셈셉셋셌셍셔셕션셜셤셥셧셨셩셰셴셸솅소속솎손솔솖솜솝솟송솥솨솩솬솰솽쇄쇈쇌쇔쇗쇘쇠쇤쇨쇰쇱쇳쇼쇽숀숄숌숍숏숑수숙순숟술숨숩숫숭숯숱숲숴쉈쉐쉑쉔쉘쉠쉥쉬쉭쉰쉴쉼쉽쉿슁슈슉슐슘슛슝스슥슨슬슭슴습슷승시식신싣실싫심십싯싱싶싸싹싻싼쌀쌈쌉쌌쌍쌓쌔쌕쌘쌜쌤쌥쌨쌩썅써썩썬썰썲썸썹썼썽쎄쎈쎌쏀쏘쏙쏜쏟쏠쏢쏨쏩쏭쏴쏵쏸쐈쐐쐤쐬쐰쐴쐼쐽쑈쑤쑥쑨쑬쑴쑵쑹쒀쒔쒜쒸쒼쓩쓰쓱쓴쓸쓺쓿씀씁씌씐씔씜씨씩씬씰씸씹씻씽아악안앉않알앍앎앓암압앗았앙앝앞애액앤앨앰앱앳앴앵야약얀얄얇얌얍얏양얕얗얘얜얠얩어억언얹얻얼얽얾엄업없엇었엉엊엌엎에엑엔엘엠엡엣엥여역엮연열엶엷염엽엾엿였영옅옆옇예옌옐옘옙옛옜오옥온올옭옮옰옳옴옵옷옹옻와왁완왈왐왑왓왔왕왜왝왠왬왯왱외왹왼욀욈욉욋욍요욕욘욜욤욥욧용우욱운울욹욺움웁웃웅워웍원월웜웝웠웡웨웩웬웰웸웹웽위윅윈윌윔윕윗윙유육윤율윰윱윳융윷으윽은을읊음읍읏응읒읓읔읕읖읗의읜읠읨읫이익인일읽읾잃임입잇있잉잊잎자작잔잖잗잘잚잠잡잣잤장잦재잭잰잴잼잽잿쟀쟁쟈쟉쟌쟎쟐쟘쟝쟤쟨쟬저적전절젊점접젓정젖제젝젠젤젬젭젯젱져젼졀졈졉졌졍졔조족존졸졺좀좁좃종좆좇좋좌좍좔좝좟좡좨좼좽죄죈죌죔죕죗죙죠죡죤죵주죽준줄줅줆줌줍줏중줘줬줴쥐쥑쥔쥘쥠쥡쥣쥬쥰쥴쥼즈즉즌즐즘즙즛증지직진짇질짊짐집짓징짖짙짚짜짝짠짢짤짧짬짭짯짰짱째짹짼쨀쨈쨉쨋쨌쨍쨔쨘쨩쩌쩍쩐쩔쩜쩝쩟쩠쩡쩨쩽쪄쪘쪼쪽쫀쫄쫌쫍쫏쫑쫓쫘쫙쫠쫬쫴쬈쬐쬔쬘쬠쬡쭁쭈쭉쭌쭐쭘쭙쭝쭤쭸쭹쮜쮸쯔쯤쯧쯩찌찍찐찔찜찝찡찢찧차착찬찮찰참찹찻찼창찾채책챈챌챔챕챗챘챙챠챤챦챨챰챵처척천철첨첩첫첬청체첵첸첼쳄쳅쳇쳉쳐쳔쳤쳬쳰촁초촉촌촐촘촙촛총촤촨촬촹최쵠쵤쵬쵭쵯쵱쵸춈추축춘출춤춥춧충춰췄췌췐취췬췰췸췹췻췽츄츈츌츔츙츠측츤츨츰츱츳층치칙친칟칠칡침칩칫칭카칵칸칼캄캅캇캉캐캑캔캘캠캡캣캤캥캬캭컁커컥컨컫컬컴컵컷컸컹케켁켄켈켐켑켓켕켜켠켤켬켭켯켰켱켸코콕콘콜콤콥콧콩콰콱콴콸쾀쾅쾌쾡쾨쾰쿄쿠쿡쿤쿨쿰쿱쿳쿵쿼퀀퀄퀑퀘퀭퀴퀵퀸퀼큄큅큇큉큐큔큘큠크큭큰클큼큽킁키킥킨킬킴킵킷킹타탁탄탈탉탐탑탓탔탕태택탠탤탬탭탯탰탱탸턍터턱턴털턺텀텁텃텄텅테텍텐텔템텝텟텡텨텬텼톄톈토톡톤톨톰톱톳통톺톼퇀퇘퇴퇸툇툉툐투툭툰툴툼툽툿퉁퉈퉜퉤튀튁튄튈튐튑튕튜튠튤튬튱트특튼튿틀틂틈틉틋틔틘틜틤틥티틱틴틸팀팁팃팅파팍팎판팔팖팜팝팟팠팡팥패팩팬팰팸팹팻팼팽퍄퍅퍼퍽펀펄펌펍펏펐펑페펙펜펠펨펩펫펭펴편펼폄폅폈평폐폘폡폣포폭폰폴폼폽폿퐁퐈퐝푀푄표푠푤푭푯푸푹푼푿풀풂품풉풋풍풔풩퓌퓐퓔퓜퓟퓨퓬퓰퓸퓻퓽프픈플픔픕픗피픽핀필핌핍핏핑하학한할핥함합핫항해핵핸핼햄햅햇했행햐향허헉헌헐헒험헙헛헝헤헥헨헬헴헵헷헹혀혁현혈혐협혓혔형혜혠혤혭호혹혼홀홅홈홉홋홍홑화확환활홧황홰홱홴횃횅회획횐횔횝횟횡효횬횰횹횻후훅훈훌훑훔훗훙훠훤훨훰훵훼훽휀휄휑휘휙휜휠휨휩휫휭휴휵휸휼흄흇흉흐흑흔흖흗흘흙흠흡흣흥흩희흰흴흼흽힁히힉힌힐힘힙힛힝()%?!.\'\",',
                        help='character label')
    parser.add_argument('--sensitive', action='store_true', help='for sensitive character mode')
    parser.add_argument('--PAD', action='store_true', help='whether to keep ratio then pad for image resize')
    """ Model Architecture """
    parser.add_argument('--Transformation', type=str, required=True, help='Transformation stage. None|TPS')
    parser.add_argument('--FeatureExtraction', type=str, required=True, help='FeatureExtraction stage. VGG|RCNN|ResNet')
    parser.add_argument('--SequenceModeling', type=str, required=True, help='SequenceModeling stage. None|BiLSTM')
    parser.add_argument('--Prediction', type=str, required=True, help='Prediction stage. CTC|Attn')
    parser.add_argument('--num_fiducial', type=int, default=20, help='number of fiducial points of TPS-STN')
    parser.add_argument('--input_channel', type=int, default=1, help='the number of input channel of Feature extractor')
    parser.add_argument('--output_channel', type=int, default=512,
                        help='the number of output channel of Feature extractor')
    parser.add_argument('--hidden_size', type=int, default=256, help='the size of the LSTM hidden state')
    print(torch.cuda.get_device_name(0))
    print("cuda is available ", torch.cuda.is_available())
    opt = parser.parse_args()

    """ vocab / character number configuration """
    if opt.sensitive:
        opt.character = string.printable[:-6]  # same with ASTER setting (use 94 char).

    cudnn.benchmark = True
    cudnn.deterministic = True
    opt.num_gpu = torch.cuda.device_count()
    # print(opt.image_folder)

    imgPath = "./demo_image3/demo_8.jpg"
    opt.image_folder = "./temps" #craft로 분리된 문자열이 저장되는 곳입니다
    craftModel=cDemo.loadModel()
    model = setModel(opt)

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    #cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    #cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    while (True):
        ret, frame = cap.read()  # Read 결과와 frame

        if (ret):
            imgPath="./webcamTempImage.jpg"
            # src=frame
            curFrame=copy.deepcopy(frame)
            frame,cropped,pos=videomaker.setRoi(frame,cap)
            cv2.imwrite(imgPath,cropped)
            img, points = craftOperation(imgPath, craftModel, dirPath=opt.image_folder)
            texts = demo(opt, model)
            # putText(points, ["1", "2", "3", "4", "5", "6", "7"])
            img = putText(img, points, texts)
            frame[pos[0]:pos[1],pos[2]:pos[3]]=img
            img=frame
            # img = putText(src, points, texts)

            cv2.namedWindow("img", cv2.WINDOW_NORMAL)
            cv2.imshow("img", img)
            # shutil.rmtree(opt.image_folder)
            if os.path.exists(opt.image_folder):
                for file in os.scandir(opt.image_folder):
                    os.remove(file.path)

            # cv2.imshow('frame_gray', gray)    # Gray 화면 출력
            if cv2.waitKey(1) == ord('q'):
                break
    cap.release()




# python demo2.py --Transformation TPS --FeatureExtraction ResNet --SequenceModeling BiLSTM --Prediction CTC --image_folder demo_image2/ --saved_model best_accuracy.pth --imgH 64 --imgW 200

# python -m cProfile -o runTime.prof demo.py --Transformation TPS --FeatureExtraction ResNet --SequenceModeling BiLSTM --Prediction CTC --image_folder demo_image3/ --saved_model best_accuracy.pth --imgH 64 --imgW 200

# python demo2.py --Transformation TPS --FeatureExtraction ResNet --SequenceModeling BiLSTM --Prediction CTC --image_folder demo_image2/ --saved_model best_accuracy.pth --imgH 64 --imgW 200





'''
아래는 장 단위로 처리하게 변환

'''
# # -*- coding: utf-8 -*-
# import string
# import argparse
#
# import torch
# import torch.backends.cudnn as cudnn
# import torch.utils.data
# import torch.nn.functional as F
#
# from utils import CTCLabelConverter, AttnLabelConverter
# from dataset import RawDataset2, AlignCollate
# from model import Model
# from craftPytorch import cDemo
#
# device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
# import cv2
#
#
# def setModel(opt):
#     """ model configuration """
#     if 'CTC' in opt.Prediction:
#         converter = CTCLabelConverter(opt.character)
#     else:
#         converter = AttnLabelConverter(opt.character)
#     opt.num_class = len(converter.character)
#
#     if opt.rgb:
#         opt.input_channel = 3
#     model = Model(opt)
#     print('model input parameters', opt.imgH, opt.imgW, opt.num_fiducial, opt.input_channel, opt.output_channel,
#           opt.hidden_size, opt.num_class, opt.batch_max_length, opt.Transformation, opt.FeatureExtraction,
#           opt.SequenceModeling, opt.Prediction)
#     model = torch.nn.DataParallel(model).to(device)
#
#     # load model
#     print('loading pretrained model from %s' % opt.saved_model)
#     model.load_state_dict(torch.load(opt.saved_model, map_location=device))
#     return (model,converter)
# def craftTest(imgPath):
#
#     imgs,img=cDemo.main(imgPath)
#     # for i in imgs:
#     #     cv2.imshow("i",i)
#     #     cv2.waitKey(0)
#     img=cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
#     cv2.namedWindow("1",cv2.WINDOW_NORMAL)
#     cv2.imshow("1", img)
#     cv2.waitKey(0)
#
#
# def demo(opt,model,imgPath):
#     model,converter=model
#     # prepare data. two demo images from https://github.com/bgshih/crnn#run-demo
#     AlignCollate_demo = AlignCollate(imgH=opt.imgH, imgW=opt.imgW, keep_ratio_with_pad=opt.PAD)
#     demo_data = RawDataset2(opt=opt,imgPath=imgPath)  # use RawDataset
#
#     demo_loader = torch.utils.data.DataLoader(
#         demo_data, batch_size=opt.batch_size,
#         shuffle=False,
#         num_workers=int(opt.workers),
#         collate_fn=AlignCollate_demo, pin_memory=True)
#     # print(demo_loader)
#     # predict
#     model.eval()
#     cnt=0
#     with torch.no_grad():
#         for image_tensors, image_path_list in demo_loader:
#             # print(cnt)
#             # craftTest(demo_data.__getitem__(cnt)[1])
#             # cnt+=1
#             print(image_path_list)
#
#             batch_size = image_tensors.size(0)
#             image = image_tensors.to(device)
#
#             # For max length prediction
#             length_for_pred = torch.IntTensor([opt.batch_max_length] * batch_size).to(device)
#             text_for_pred = torch.LongTensor(batch_size, opt.batch_max_length + 1).fill_(0).to(device)
#
#             if 'CTC' in opt.Prediction:
#                 # print(image)
#                 print(type(model))
#                 preds = model(image, text_for_pred)
#                 # print("여기1")
#                 # Select max probabilty (greedy decoding) then decode index to character
#                 preds_size = torch.IntTensor([preds.size(1)] * batch_size)
#                 _, preds_index = preds.max(2)
#                 # preds_index = preds_index.view(-1)
#                 preds_str = converter.decode(preds_index, preds_size)
#
#             else:
#                 preds = model(image, text_for_pred, is_train=False)
#                 # select max probabilty (greedy decoding) then decode index to character
#                 _, preds_index = preds.max(2)
#                 preds_str = converter.decode(preds_index, length_for_pred)
#
#             log = open(f'./log_demo_result.txt', 'a')
#             dashed_line = '-' * 80
#             head = f'{"image_path":25s}\t{"predicted_labels":25s}\tconfidence score'
#
#             print(f'{dashed_line}\n{head}\n{dashed_line}')
#             log.write(f'{dashed_line}\n{head}\n{dashed_line}\n')
#
#             preds_prob = F.softmax(preds, dim=2)
#             preds_max_prob, _ = preds_prob.max(dim=2)
#             for img_name, pred, pred_max_prob in zip(image_path_list, preds_str, preds_max_prob):
#                 if 'Attn' in opt.Prediction:
#                     pred_EOS = pred.find('[s]')
#                     pred = pred[:pred_EOS]  # prune after "end of sentence" token ([s])
#                     pred_max_prob = pred_max_prob[:pred_EOS]
#
#                 # calculate confidence score (= multiply of pred_max_prob)
#                 confidence_score = pred_max_prob.cumprod(dim=0)[-1]
#
#                 print(f'{img_name:25s}\t{pred:25s}\t{confidence_score:0.4f}')
#                 log.write(f'{img_name:25s}\t{pred:25s}\t{confidence_score:0.4f}\n')
#
#             log.close()
#
#
# if __name__ == '__main__':
#     parser = argparse.ArgumentParser()
#     parser.add_argument('--image_folder', required=True, help='path to image_folder which contains text images')
#     parser.add_argument('--workers', type=int, help='number of data loading workers', default=4)
#     parser.add_argument('--batch_size', type=int, default=192, help='input batch size')
#     parser.add_argument('--saved_model', required=True, help="path to saved_model to evaluation")
#     """ Data processing """
#     parser.add_argument('--batch_max_length', type=int, default=25, help='maximum-label-length')
#     parser.add_argument('--imgH', type=int, default=32, help='the height of the input image')
#     parser.add_argument('--imgW', type=int, default=100, help='the width of the input image')
#     parser.add_argument('--rgb', action='store_true', help='use rgb input')
#     parser.add_argument('--character', type=str,
#                         default='0123456789abcdefghijklmnopqrstuvwxyz가각간갇갈감갑값갓강갖같갚갛개객걀걔거걱건걷걸검겁것겉게겨격겪견결겹경곁계고곡곤곧골곰곱곳공과관광괜괴굉교구국군굳굴굵굶굽궁권귀귓규균귤그극근글긁금급긋긍기긴길김깅깊까깍깎깐깔깜깝깡깥깨꺼꺾껌껍껏껑께껴꼬꼭꼴꼼꼽꽂꽃꽉꽤꾸꾼꿀꿈뀌끄끈끊끌끓끔끗끝끼낌나낙낚난날낡남납낫낭낮낯낱낳내냄냇냉냐냥너넉넌널넓넘넣네넥넷녀녁년념녕노녹논놀놈농높놓놔뇌뇨누눈눕뉘뉴늄느늑는늘늙능늦늬니닐님다닥닦단닫달닭닮담답닷당닿대댁댐댓더덕던덜덟덤덥덧덩덮데델도독돈돌돕돗동돼되된두둑둘둠둡둥뒤뒷드득든듣들듬듭듯등디딩딪따딱딴딸땀땅때땜떠떡떤떨떻떼또똑뚜뚫뚱뛰뜨뜩뜯뜰뜻띄라락란람랍랑랗래랜램랫략량러럭런럴럼럽럿렁렇레렉렌려력련렬렵령례로록론롬롭롯료루룩룹룻뤄류륙률륭르른름릇릎리릭린림립릿링마막만많말맑맘맙맛망맞맡맣매맥맨맵맺머먹먼멀멈멋멍멎메멘멩며면멸명몇모목몬몰몸몹못몽묘무묵묶문묻물뭄뭇뭐뭘뭣므미민믿밀밉밌및밑바박밖반받발밝밟밤밥방밭배백뱀뱃뱉버번벌범법벗베벤벨벼벽변별볍병볕보복볶본볼봄봇봉뵈뵙부북분불붉붐붓붕붙뷰브븐블비빌빔빗빚빛빠빡빨빵빼뺏뺨뻐뻔뻗뼈뼉뽑뿌뿐쁘쁨사삭산살삶삼삿상새색샌생샤서석섞선설섬섭섯성세섹센셈셋셔션소속손솔솜솟송솥쇄쇠쇼수숙순숟술숨숫숭숲쉬쉰쉽슈스슨슬슴습슷승시식신싣실싫심십싯싱싶싸싹싼쌀쌍쌓써썩썰썹쎄쏘쏟쑤쓰쓴쓸씀씌씨씩씬씹씻아악안앉않알앓암압앗앙앞애액앨야약얀얄얇양얕얗얘어억언얹얻얼엄업없엇엉엊엌엎에엔엘여역연열엷염엽엿영옆예옛오옥온올옮옳옷옹와완왕왜왠외왼요욕용우욱운울움웃웅워원월웨웬위윗유육율으윽은을음응의이익인일읽잃임입잇있잊잎자작잔잖잘잠잡잣장잦재쟁쟤저적전절젊점접젓정젖제젠젯져조족존졸좀좁종좋좌죄주죽준줄줌줍중쥐즈즉즌즐즘증지직진질짐집짓징짙짚짜짝짧째쨌쩌쩍쩐쩔쩜쪽쫓쭈쭉찌찍찢차착찬찮찰참찻창찾채책챔챙처척천철첩첫청체쳐초촉촌촛총촬최추축춘출춤춥춧충취츠측츰층치칙친칠침칫칭카칸칼캄캐캠커컨컬컴컵컷케켓켜코콘콜콤콩쾌쿄쿠퀴크큰클큼키킬타탁탄탈탑탓탕태택탤터턱턴털텅테텍텔템토톤톨톱통퇴투툴툼퉁튀튜트특튼튿틀틈티틱팀팅파팎판팔팝패팩팬퍼퍽페펜펴편펼평폐포폭폰표푸푹풀품풍퓨프플픔피픽필핏핑하학한할함합항해핵핸햄햇행향허헌험헤헬혀현혈협형혜호혹혼홀홈홉홍화확환활황회획횟횡효후훈훌훔훨휘휴흉흐흑흔흘흙흡흥흩희흰히힘?!',
#                         help='character label')
#     parser.add_argument('--sensitive', action='store_true', help='for sensitive character mode')
#     parser.add_argument('--PAD', action='store_true', help='whether to keep ratio then pad for image resize')
#     """ Model Architecture """
#     parser.add_argument('--Transformation', type=str, required=True, help='Transformation stage. None|TPS')
#     parser.add_argument('--FeatureExtraction', type=str, required=True, help='FeatureExtraction stage. VGG|RCNN|ResNet')
#     parser.add_argument('--SequenceModeling', type=str, required=True, help='SequenceModeling stage. None|BiLSTM')
#     parser.add_argument('--Prediction', type=str, required=True, help='Prediction stage. CTC|Attn')
#     parser.add_argument('--num_fiducial', type=int, default=20, help='number of fiducial points of TPS-STN')
#     parser.add_argument('--input_channel', type=int, default=1, help='the number of input channel of Feature extractor')
#     parser.add_argument('--output_channel', type=int, default=512,
#                         help='the number of output channel of Feature extractor')
#     parser.add_argument('--hidden_size', type=int, default=256, help='the size of the LSTM hidden state')
#
#     opt = parser.parse_args()
#
#     """ vocab / character number configuration """
#     if opt.sensitive:
#         opt.character = string.printable[:-6]  # same with ASTER setting (use 94 char).
#
#     cudnn.benchmark = True
#     cudnn.deterministic = True
#     opt.num_gpu = torch.cuda.device_count()
#     # print(opt.image_folder)
#     import time
#     start=time.time()
#     model=setModel(opt)
#     elapsed1=time.time()-start
#     start = time.time()
#     imgPath="./demo_image3/demo_1.jpg"
#     imgPath = "./demo_image3/demo_1.jpg"
#     demo(opt,model,imgPath)
#     elapsed2=time.time()-start
#     print(elapsed1,elapsed2)
#
# # python -m cProfile -o runTime.prof demo.py --Transformation TPS --FeatureExtraction ResNet --SequenceModeling BiLSTM --Prediction CTC --image_folder demo_image3/ --saved_model best_accuracy.pth --imgH 64 --imgW 200
#
# # python demo2.py --Transformation TPS --FeatureExtraction ResNet --SequenceModeling BiLSTM --Prediction CTC --image_folder demo_image2/ --saved_model best_accuracy.pth --imgH 64 --imgW 200
#
#

# # -*- coding: utf-8 -*-
# import string
# import argparse
#
# import torch
# import torch.backends.cudnn as cudnn
# import torch.utils.data
# import torch.nn.functional as F
#
# from utils import CTCLabelConverter, AttnLabelConverter
# from dataset import RawDataset, AlignCollate
# from model import Model
# from craftPytorch import cDemo
# from PIL import ImageFont, ImageDraw, Image
# device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
# import cv2
# import numpy as np
# import shutil
# import time
# import videomaker
# def setModel(opt):
#     start=time.time()
#     """ model configuration """
#     if 'CTC' in opt.Prediction:
#         converter = CTCLabelConverter(opt.character)
#     else:
#         converter = AttnLabelConverter(opt.character)
#     opt.num_class = len(converter.character)
#
#     if opt.rgb:
#         opt.input_channel = 3
#     model = Model(opt)
#     # print('model input parameters', opt.imgH, opt.imgW, opt.num_fiducial, opt.input_channel, opt.output_channel,
#     #       opt.hidden_size, opt.num_class, opt.batch_max_length, opt.Transformation, opt.FeatureExtraction,
#     #       opt.SequenceModeling, opt.Prediction)
#     model = torch.nn.DataParallel(model).to(device)
#
#     # load model
#     # print('loading pretrained model from %s' % opt.saved_model)
#     print("text recognition model load",time.time()-start)
#     model.load_state_dict(torch.load(opt.saved_model, map_location=device))
#     return (model,converter)
#
#
#
# def demo(opt,model):
#     model,converter=model
#     # prepare data. two demo images from https://github.com/bgshih/crnn#run-demo
#     AlignCollate_demo = AlignCollate(imgH=opt.imgH, imgW=opt.imgW, keep_ratio_with_pad=opt.PAD)
#     demo_data = RawDataset(root=opt.image_folder, opt=opt)  # use RawDataset
#
#     demo_loader = torch.utils.data.DataLoader(
#         demo_data, batch_size=opt.batch_size,
#         shuffle=False,
#         # num_workers=int(opt.workers),
#         num_workers=int(0),
#         collate_fn=AlignCollate_demo, pin_memory=True)
#     # print(demo_loader)
#     # predict
#     model.eval()
#     cnt=0
#     texts=[]
#     with torch.no_grad():
#         for image_tensors, image_path_list in demo_loader:
#             # print(cnt)
#             # craftTest(demo_data.__getitem__(cnt)[1])
#             # cnt+=1
#             # print(image_path_list)
#
#             batch_size = image_tensors.size(0)
#             image = image_tensors.to(device)
#
#             # For max length prediction
#             length_for_pred = torch.IntTensor([opt.batch_max_length] * batch_size).to(device)
#             text_for_pred = torch.LongTensor(batch_size, opt.batch_max_length + 1).fill_(0).to(device)
#
#             if 'CTC' in opt.Prediction:
#                 # print(image)
#                 # print(type(model))
#                 preds = model(image, text_for_pred)
#                 # print("여기1")
#                 # Select max probabilty (greedy decoding) then decode index to character
#                 preds_size = torch.IntTensor([preds.size(1)] * batch_size)
#                 _, preds_index = preds.max(2)
#                 # preds_index = preds_index.view(-1)
#                 preds_str = converter.decode(preds_index, preds_size)
#
#             else:
#                 preds = model(image, text_for_pred, is_train=False)
#                 # select max probabilty (greedy decoding) then decode index to character
#                 _, preds_index = preds.max(2)
#                 preds_str = converter.decode(preds_index, length_for_pred)
#
#             # log = open(f'./log_demo_result.txt', 'a')
#             dashed_line = '-' * 80
#             head = f'{"image_path":25s}\t{"predicted_labels":25s}\tconfidence score'
#
#             # print(f'{dashed_line}\n{head}\n{dashed_line}')
#             # log.write(f'{dashed_line}\n{head}\n{dashed_line}\n')
#
#             preds_prob = F.softmax(preds, dim=2)
#             preds_max_prob, _ = preds_prob.max(dim=2)
#             for img_name, pred, pred_max_prob in zip(image_path_list, preds_str, preds_max_prob):
#                 if 'Attn' in opt.Prediction:
#                     pred_EOS = pred.find('[s]')
#                     pred = pred[:pred_EOS]  # prune after "end of sentence" token ([s])
#                     pred_max_prob = pred_max_prob[:pred_EOS]
#
#                 # calculate confidence score (= multiply of pred_max_prob)
#                 confidence_score = pred_max_prob.cumprod(dim=0)[-1]
#                 texts.append(pred)
#                 # print(f'{img_name:25s}\t{pred:25s}\t{confidence_score:0.4f}')
#                 # log.write(f'{img_name:25s}\t{pred:25s}\t{confidence_score:0.4f}\n')
#
#             # log.close()
#     # print('-' * 80)
#     # print(texts)
#     del texts[len(texts)-1]
#     return texts
# import pathlib
# import os
# def saveCraftResult(dirPath,imgs,img):
#     cnt=0
#     for i in imgs:
#         savePath= os.path.join(dirPath, str(cnt)+".jpg")
#         cv2.imwrite(savePath,i)
#         cnt+=1
#     savePath = os.path.join(dirPath, "result" + ".jpg")
#     cv2.imwrite(savePath, img)
#
#     #
#     # ROOT_DIR = dirPath
#     # image1 = pathlib.Path(os.path.join(ROOT_DIR))
#     # image_list = list(image1.glob('*.jpg'))
#     # 이건 실험 코드 175부터
# def getCraftResult(imagePath,craftModel):
#     imgs, img,points = cDemo.main(imagePath,craftModel)
#     # print(len(imgs))
#     resultImgs=[]
#     cnt=0
#     for i in imgs:
#         rows,cols,_=i.shape
#         if(rows != 0 and cols != 0):
#             # print(i.shape)
#             resultImgs.append(i)
#             # cv2.imshow("img",i)
#             # cv2.waitKey(0)
#         else:
#             print("len(imgs)",len(imgs),'len(points)',len(points),'cnt',cnt)
#             del points[cnt]
#             cnt-=1
#         cnt+=1
#     return resultImgs, img,points
# def putText(img,points,texts):
#     # print(len(points),len(texts))
#     fontSize=16
#     font = ImageFont.truetype('malgun.ttf', fontSize)
#     img_pil = Image.fromarray(img)
#     draw = ImageDraw.Draw(img_pil)
#     for i in range(len(points)):
#         point=points[i]
#         text=texts[i]
#         draw.text((point[1],point[0]), text, font=font, fill=(255, 0, 255, 0))
#         # cv2.putText는 한글안됨
#         # cv2.putText(img, text, (point[1],point[0]), cv2.FONT_HERSHEY_SIMPLEX, 5, (255, 0, 255), 5, cv2.LINE_AA)
#     img = np.array(img_pil)
#
#     return img
#
# def craftOperation(imgPath,craftModel,dirPath):
#     imgs,img,points=getCraftResult(imgPath,craftModel)
#     if not (os.path.isdir(dirPath)):
#         os.makedirs(os.path.join(dirPath))
#     saveCraftResult(dirPath,imgs,img)
#     return img,points
#
#
# if __name__ == '__main__':
#     parser = argparse.ArgumentParser()
#     parser.add_argument('--image_folder',help='path to image_folder which contains text images')
#
#     parser.add_argument('--workers', type=int, help='number of data loading workers', default=4)
#     parser.add_argument('--batch_size', type=int, default=192, help='input batch size')
#     parser.add_argument('--saved_model', required=True, help="path to saved_model to evaluation")
#     """ Data processing """
#     parser.add_argument('--batch_max_length', type=int, default=25, help='maximum-label-length')
#     parser.add_argument('--imgH', type=int, default=32, help='the height of the input image')
#     parser.add_argument('--imgW', type=int, default=100, help='the width of the input image')
#     parser.add_argument('--rgb', action='store_true', help='use rgb input')
#     # parser.add_argument('--character', type=str,
#     #                     default='0123456789abcdefghijklmnopqrstuvwxyz가각간갇갈감갑값갓강갖같갚갛개객걀걔거걱건걷걸검겁것겉게겨격겪견결겹경곁계고곡곤곧골곰곱곳공과관광괜괴굉교구국군굳굴굵굶굽궁권귀귓규균귤그극근글긁금급긋긍기긴길김깅깊까깍깎깐깔깜깝깡깥깨꺼꺾껌껍껏껑께껴꼬꼭꼴꼼꼽꽂꽃꽉꽤꾸꾼꿀꿈뀌끄끈끊끌끓끔끗끝끼낌나낙낚난날낡남납낫낭낮낯낱낳내냄냇냉냐냥너넉넌널넓넘넣네넥넷녀녁년념녕노녹논놀놈농높놓놔뇌뇨누눈눕뉘뉴늄느늑는늘늙능늦늬니닐님다닥닦단닫달닭닮담답닷당닿대댁댐댓더덕던덜덟덤덥덧덩덮데델도독돈돌돕돗동돼되된두둑둘둠둡둥뒤뒷드득든듣들듬듭듯등디딩딪따딱딴딸땀땅때땜떠떡떤떨떻떼또똑뚜뚫뚱뛰뜨뜩뜯뜰뜻띄라락란람랍랑랗래랜램랫략량러럭런럴럼럽럿렁렇레렉렌려력련렬렵령례로록론롬롭롯료루룩룹룻뤄류륙률륭르른름릇릎리릭린림립릿링마막만많말맑맘맙맛망맞맡맣매맥맨맵맺머먹먼멀멈멋멍멎메멘멩며면멸명몇모목몬몰몸몹못몽묘무묵묶문묻물뭄뭇뭐뭘뭣므미민믿밀밉밌및밑바박밖반받발밝밟밤밥방밭배백뱀뱃뱉버번벌범법벗베벤벨벼벽변별볍병볕보복볶본볼봄봇봉뵈뵙부북분불붉붐붓붕붙뷰브븐블비빌빔빗빚빛빠빡빨빵빼뺏뺨뻐뻔뻗뼈뼉뽑뿌뿐쁘쁨사삭산살삶삼삿상새색샌생샤서석섞선설섬섭섯성세섹센셈셋셔션소속손솔솜솟송솥쇄쇠쇼수숙순숟술숨숫숭숲쉬쉰쉽슈스슨슬슴습슷승시식신싣실싫심십싯싱싶싸싹싼쌀쌍쌓써썩썰썹쎄쏘쏟쑤쓰쓴쓸씀씌씨씩씬씹씻아악안앉않알앓암압앗앙앞애액앨야약얀얄얇양얕얗얘어억언얹얻얼엄업없엇엉엊엌엎에엔엘여역연열엷염엽엿영옆예옛오옥온올옮옳옷옹와완왕왜왠외왼요욕용우욱운울움웃웅워원월웨웬위윗유육율으윽은을음응의이익인일읽잃임입잇있잊잎자작잔잖잘잠잡잣장잦재쟁쟤저적전절젊점접젓정젖제젠젯져조족존졸좀좁종좋좌죄주죽준줄줌줍중쥐즈즉즌즐즘증지직진질짐집짓징짙짚짜짝짧째쨌쩌쩍쩐쩔쩜쪽쫓쭈쭉찌찍찢차착찬찮찰참찻창찾채책챔챙처척천철첩첫청체쳐초촉촌촛총촬최추축춘출춤춥춧충취츠측츰층치칙친칠침칫칭카칸칼캄캐캠커컨컬컴컵컷케켓켜코콘콜콤콩쾌쿄쿠퀴크큰클큼키킬타탁탄탈탑탓탕태택탤터턱턴털텅테텍텔템토톤톨톱통퇴투툴툼퉁튀튜트특튼튿틀틈티틱팀팅파팎판팔팝패팩팬퍼퍽페펜펴편펼평폐포폭폰표푸푹풀품풍퓨프플픔피픽필핏핑하학한할함합항해핵핸햄햇행향허헌험헤헬혀현혈협형혜호혹혼홀홈홉홍화확환활황회획횟횡효후훈훌훔훨휘휴흉흐흑흔흘흙흡흥흩희흰히힘?!',
#     #                     help='character label')
#     # parser.add_argument('--character', type=str,
#     #                     default='가각간갇갈감갑값갓강갖같갚갛개객걀걔거걱건걷걸검겁것겉게겨격겪견결겹경곁계고곡곤곧골곰곱곳공과관광괜괴굉교구국군굳굴굵굶굽궁권귀귓규균귤그극근글긁금급긋긍기긴길김깅깊까깍깎깐깔깜깝깡깥깨꺼꺾껌껍껏껑께껴꼬꼭꼴꼼꼽꽂꽃꽉꽤꾸꾼꿀꿈뀌끄끈끊끌끓끔끗끝끼낌나낙낚난날낡남납낫낭낮낯낱낳내냄냇냉냐냥너넉넌널넓넘넣네넥넷녀녁년념녕노녹논놀놈농높놓놔뇌뇨누눈눕뉘뉴늄느늑는늘늙능늦늬니닐님다닥닦단닫달닭닮담답닷당닿대댁댐댓더덕던덜덟덤덥덧덩덮데델도독돈돌돕돗동돼되된두둑둘둠둡둥뒤뒷드득든듣들듬듭듯등디딩딪따딱딴딸땀땅때땜떠떡떤떨떻떼또똑뚜뚫뚱뛰뜨뜩뜯뜰뜻띄라락란람랍랑랗래랜램랫략량러럭런럴럼럽럿렁렇레렉렌려력련렬렵령례로록론롬롭롯료루룩룹룻뤄류륙률륭르른름릇릎리릭린림립릿링마막만많말맑맘맙맛망맞맡맣매맥맨맵맺머먹먼멀멈멋멍멎메멘멩며면멸명몇모목몬몰몸몹못몽묘무묵묶문묻물뭄뭇뭐뭘뭣므미민믿밀밉밌및밑바박밖반받발밝밟밤밥방밭배백뱀뱃뱉버번벌범법벗베벤벨벼벽변별볍병볕보복볶본볼봄봇봉뵈뵙부북분불붉붐붓붕붙뷰브븐블비빌빔빗빚빛빠빡빨빵빼뺏뺨뻐뻔뻗뼈뼉뽑뿌뿐쁘쁨사삭산살삶삼삿상새색샌생샤서석섞선설섬섭섯성세섹센셈셋셔션소속손솔솜솟송솥쇄쇠쇼수숙순숟술숨숫숭숲쉬쉰쉽슈스슨슬슴습슷승시식신싣실싫심십싯싱싶싸싹싼쌀쌍쌓써썩썰썹쎄쏘쏟쑤쓰쓴쓸씀씌씨씩씬씹씻아악안앉않알앓암압앗앙앞애액앨야약얀얄얇양얕얗얘어억언얹얻얼엄업없엇엉엊엌엎에엔엘여역연열엷염엽엿영옆예옛오옥온올옮옳옷옹와완왕왜왠외왼요욕용우욱운울움웃웅워원월웨웬위윗유육율으윽은을음응의이익인일읽잃임입잇있잊잎자작잔잖잘잠잡잣장잦재쟁쟤저적전절젊점접젓정젖제젠젯져조족존졸좀좁종좋좌죄주죽준줄줌줍중쥐즈즉즌즐즘증지직진질짐집짓징짙짚짜짝짧째쨌쩌쩍쩐쩔쩜쪽쫓쭈쭉찌찍찢차착찬찮찰참찻창찾채책챔챙처척천철첩첫청체쳐초촉촌촛총촬최추축춘출춤춥춧충취츠측츰층치칙친칠침칫칭카칸칼캄캐캠커컨컬컴컵컷케켓켜코콘콜콤콩쾌쿄쿠퀴크큰클큼키킬타탁탄탈탑탓탕태택탤터턱턴털텅테텍텔템토톤톨톱통퇴투툴툼퉁튀튜트특튼튿틀틈티틱팀팅파팎판팔팝패팩팬퍼퍽페펜펴편펼평폐포폭폰표푸푹풀품풍퓨프플픔피픽필핏핑하학한할함합항해핵핸햄햇행향허헌험헤헬혀현혈협형혜호혹혼홀홈홉홍화확환활황회획횟횡효후훈훌훔훨휘휴흉흐흑흔흘흙흡흥흩희흰히힘',
#     #                     help='character label')
#     parser.add_argument('--character', type=str,
#                         default='0123456789abcdefghijklmnopqrstuvwxyz가각간갇갈감갑값갓강갖같갚갛개객걀걔거걱건걷걸검겁것겉게겨격겪견결겹경곁계고곡곤곧골곰곱곳공과관광괜괴굉교구국군굳굴굵굶굽궁권귀귓규균귤그극근글긁금급긋긍기긴길김깅깊까깍깎깐깔깜깝깡깥깨꺼꺾껌껍껏껑께껴꼬꼭꼴꼼꼽꽂꽃꽉꽤꾸꾼꿀꿈뀌끄끈끊끌끓끔끗끝끼낌나낙낚난날낡남납낫낭낮낯낱낳내냄냇냉냐냥너넉넌널넓넘넣네넥넷녀녁년념녕노녹논놀놈농높놓놔뇌뇨누눈눕뉘뉴늄느늑는늘늙능늦늬니닐님다닥닦단닫달닭닮담답닷당닿대댁댐댓더덕던덜덟덤덥덧덩덮데델도독돈돌돕돗동돼되된두둑둘둠둡둥뒤뒷드득든듣들듬듭듯등디딩딪따딱딴딸땀땅때땜떠떡떤떨떻떼또똑뚜뚫뚱뛰뜨뜩뜯뜰뜻띄라락란람랍랑랗래랜램랫략량러럭런럴럼럽럿렁렇레렉렌려력련렬렵령례로록론롬롭롯료루룩룹룻뤄류륙률륭르른름릇릎리릭린림립릿링마막만많말맑맘맙맛망맞맡맣매맥맨맵맺머먹먼멀멈멋멍멎메멘멩며면멸명몇모목몬몰몸몹못몽묘무묵묶문묻물뭄뭇뭐뭘뭣므미민믿밀밉밌및밑바박밖반받발밝밟밤밥방밭배백뱀뱃뱉버번벌범법벗베벤벨벼벽변별볍병볕보복볶본볼봄봇봉뵈뵙부북분불붉붐붓붕붙뷰브븐블비빌빔빗빚빛빠빡빨빵빼뺏뺨뻐뻔뻗뼈뼉뽑뿌뿐쁘쁨사삭산살삶삼삿상새색샌생샤서석섞선설섬섭섯성세섹센셈셋셔션소속손솔솜솟송솥쇄쇠쇼수숙순숟술숨숫숭숲쉬쉰쉽슈스슨슬슴습슷승시식신싣실싫심십싯싱싶싸싹싼쌀쌍쌓써썩썰썹쎄쏘쏟쑤쓰쓴쓸씀씌씨씩씬씹씻아악안앉않알앓암압앗앙앞애액앨야약얀얄얇양얕얗얘어억언얹얻얼엄업없엇엉엊엌엎에엔엘여역연열엷염엽엿영옆예옛오옥온올옮옳옷옹와완왕왜왠외왼요욕용우욱운울움웃웅워원월웨웬위윗유육율으윽은을음응의이익인일읽잃임입잇있잊잎자작잔잖잘잠잡잣장잦재쟁쟤저적전절젊점접젓정젖제젠젯져조족존졸좀좁종좋좌죄주죽준줄줌줍중쥐즈즉즌즐즘증지직진질짐집짓징짙짚짜짝짧째쨌쩌쩍쩐쩔쩜쪽쫓쭈쭉찌찍찢차착찬찮찰참찻창찾채책챔챙처척천철첩첫청체쳐초촉촌촛총촬최추축춘출춤춥춧충취츠측츰층치칙친칠침칫칭카칸칼캄캐캠커컨컬컴컵컷케켓켜코콘콜콤콩쾌쿄쿠퀴크큰클큼키킬타탁탄탈탑탓탕태택탤터턱턴털텅테텍텔템토톤톨톱통퇴투툴툼퉁튀튜트특튼튿틀틈티틱팀팅파팎판팔팝패팩팬퍼퍽페펜펴편펼평폐포폭폰표푸푹풀품풍퓨프플픔피픽필핏핑하학한할함합항해핵핸햄햇행향허헌험헤헬혀현혈협형혜호혹혼홀홈홉홍화확환활황회획횟횡효후훈훌훔훨휘휴흉흐흑흔흘흙흡흥흩희흰히힘?!.\'\",',
#                         help='character label')
#     parser.add_argument('--sensitive', action='store_true', help='for sensitive character mode')
#     parser.add_argument('--PAD', action='store_true', help='whether to keep ratio then pad for image resize')
#     """ Model Architecture """
#     parser.add_argument('--Transformation', type=str, required=True, help='Transformation stage. None|TPS')
#     parser.add_argument('--FeatureExtraction', type=str, required=True, help='FeatureExtraction stage. VGG|RCNN|ResNet')
#     parser.add_argument('--SequenceModeling', type=str, required=True, help='SequenceModeling stage. None|BiLSTM')
#     parser.add_argument('--Prediction', type=str, required=True, help='Prediction stage. CTC|Attn')
#     parser.add_argument('--num_fiducial', type=int, default=20, help='number of fiducial points of TPS-STN')
#     parser.add_argument('--input_channel', type=int, default=1, help='the number of input channel of Feature extractor')
#     parser.add_argument('--output_channel', type=int, default=512,
#                         help='the number of output channel of Feature extractor')
#     parser.add_argument('--hidden_size', type=int, default=256, help='the size of the LSTM hidden state')
#     print(torch.cuda.get_device_name(0))
#     print("cuda is available ", torch.cuda.is_available())
#     opt = parser.parse_args()
#
#     """ vocab / character number configuration """
#     if opt.sensitive:
#         opt.character = string.printable[:-6]  # same with ASTER setting (use 94 char).
#
#     cudnn.benchmark = True
#     cudnn.deterministic = True
#     opt.num_gpu = torch.cuda.device_count()
#     # print(opt.image_folder)
#
#     imgPath = "./demo_image3/demo_8.jpg"
#     opt.image_folder = "./temps" #craft로 분리된 문자열이 저장되는 곳입니다
#     craftModel=cDemo.loadModel()
#     model = setModel(opt)
#
#     cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
#
#     # cap.set(cv2.CAP_PROP_FRAME_WIDTH, 4096)
#     # cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 3072)
#
#     while (True):
#         ret, frame = cap.read()  # Read 결과와 frame
#
#         if (ret):
#             imgPath="./webcamTempImage.jpg"
#             # src=frame
#             cv2.imwrite(imgPath,frame)
#             img, points = craftOperation(imgPath, craftModel, dirPath=opt.image_folder)
#             texts = demo(opt, model)
#             # putText(points, ["1", "2", "3", "4", "5", "6", "7"])
#             img = putText(img, points, texts)
#             # img = putText(src, points, texts)
#
#             cv2.namedWindow("img", cv2.WINDOW_NORMAL)
#             cv2.imshow("img", img)
#             # shutil.rmtree(opt.image_folder)
#             if os.path.exists(opt.image_folder):
#                 for file in os.scandir(opt.image_folder):
#                     os.remove(file.path)
#
#             # cv2.imshow('frame_gray', gray)    # Gray 화면 출력
#             if cv2.waitKey(1) == ord('q'):
#                 break
#     cap.release()
#



# python demo2.py --Transformation TPS --FeatureExtraction ResNet --SequenceModeling BiLSTM --Prediction CTC --image_folder demo_image2/ --saved_model best_accuracy.pth --imgH 64 --imgW 200

# python -m cProfile -o runTime.prof demo.py --Transformation TPS --FeatureExtraction ResNet --SequenceModeling BiLSTM --Prediction CTC --image_folder demo_image3/ --saved_model best_accuracy.pth --imgH 64 --imgW 200

# python demo2.py --Transformation TPS --FeatureExtraction ResNet --SequenceModeling BiLSTM --Prediction CTC --image_folder demo_image2/ --saved_model best_accuracy.pth --imgH 64 --imgW 200





'''
아래는 장 단위로 처리하게 변환

'''
# # -*- coding: utf-8 -*-
# import string
# import argparse
#
# import torch
# import torch.backends.cudnn as cudnn
# import torch.utils.data
# import torch.nn.functional as F
#
# from utils import CTCLabelConverter, AttnLabelConverter
# from dataset import RawDataset2, AlignCollate
# from model import Model
# from craftPytorch import cDemo
#
# device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
# import cv2
#
#
# def setModel(opt):
#     """ model configuration """
#     if 'CTC' in opt.Prediction:
#         converter = CTCLabelConverter(opt.character)
#     else:
#         converter = AttnLabelConverter(opt.character)
#     opt.num_class = len(converter.character)
#
#     if opt.rgb:
#         opt.input_channel = 3
#     model = Model(opt)
#     print('model input parameters', opt.imgH, opt.imgW, opt.num_fiducial, opt.input_channel, opt.output_channel,
#           opt.hidden_size, opt.num_class, opt.batch_max_length, opt.Transformation, opt.FeatureExtraction,
#           opt.SequenceModeling, opt.Prediction)
#     model = torch.nn.DataParallel(model).to(device)
#
#     # load model
#     print('loading pretrained model from %s' % opt.saved_model)
#     model.load_state_dict(torch.load(opt.saved_model, map_location=device))
#     return (model,converter)
# def craftTest(imgPath):
#
#     imgs,img=cDemo.main(imgPath)
#     # for i in imgs:
#     #     cv2.imshow("i",i)
#     #     cv2.waitKey(0)
#     img=cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
#     cv2.namedWindow("1",cv2.WINDOW_NORMAL)
#     cv2.imshow("1", img)
#     cv2.waitKey(0)
#
#
# def demo(opt,model,imgPath):
#     model,converter=model
#     # prepare data. two demo images from https://github.com/bgshih/crnn#run-demo
#     AlignCollate_demo = AlignCollate(imgH=opt.imgH, imgW=opt.imgW, keep_ratio_with_pad=opt.PAD)
#     demo_data = RawDataset2(opt=opt,imgPath=imgPath)  # use RawDataset
#
#     demo_loader = torch.utils.data.DataLoader(
#         demo_data, batch_size=opt.batch_size,
#         shuffle=False,
#         num_workers=int(opt.workers),
#         collate_fn=AlignCollate_demo, pin_memory=True)
#     # print(demo_loader)
#     # predict
#     model.eval()
#     cnt=0
#     with torch.no_grad():
#         for image_tensors, image_path_list in demo_loader:
#             # print(cnt)
#             # craftTest(demo_data.__getitem__(cnt)[1])
#             # cnt+=1
#             print(image_path_list)
#
#             batch_size = image_tensors.size(0)
#             image = image_tensors.to(device)
#
#             # For max length prediction
#             length_for_pred = torch.IntTensor([opt.batch_max_length] * batch_size).to(device)
#             text_for_pred = torch.LongTensor(batch_size, opt.batch_max_length + 1).fill_(0).to(device)
#
#             if 'CTC' in opt.Prediction:
#                 # print(image)
#                 print(type(model))
#                 preds = model(image, text_for_pred)
#                 # print("여기1")
#                 # Select max probabilty (greedy decoding) then decode index to character
#                 preds_size = torch.IntTensor([preds.size(1)] * batch_size)
#                 _, preds_index = preds.max(2)
#                 # preds_index = preds_index.view(-1)
#                 preds_str = converter.decode(preds_index, preds_size)
#
#             else:
#                 preds = model(image, text_for_pred, is_train=False)
#                 # select max probabilty (greedy decoding) then decode index to character
#                 _, preds_index = preds.max(2)
#                 preds_str = converter.decode(preds_index, length_for_pred)
#
#             log = open(f'./log_demo_result.txt', 'a')
#             dashed_line = '-' * 80
#             head = f'{"image_path":25s}\t{"predicted_labels":25s}\tconfidence score'
#
#             print(f'{dashed_line}\n{head}\n{dashed_line}')
#             log.write(f'{dashed_line}\n{head}\n{dashed_line}\n')
#
#             preds_prob = F.softmax(preds, dim=2)
#             preds_max_prob, _ = preds_prob.max(dim=2)
#             for img_name, pred, pred_max_prob in zip(image_path_list, preds_str, preds_max_prob):
#                 if 'Attn' in opt.Prediction:
#                     pred_EOS = pred.find('[s]')
#                     pred = pred[:pred_EOS]  # prune after "end of sentence" token ([s])
#                     pred_max_prob = pred_max_prob[:pred_EOS]
#
#                 # calculate confidence score (= multiply of pred_max_prob)
#                 confidence_score = pred_max_prob.cumprod(dim=0)[-1]
#
#                 print(f'{img_name:25s}\t{pred:25s}\t{confidence_score:0.4f}')
#                 log.write(f'{img_name:25s}\t{pred:25s}\t{confidence_score:0.4f}\n')
#
#             log.close()
#
#
# if __name__ == '__main__':
#     parser = argparse.ArgumentParser()
#     parser.add_argument('--image_folder', required=True, help='path to image_folder which contains text images')
#     parser.add_argument('--workers', type=int, help='number of data loading workers', default=4)
#     parser.add_argument('--batch_size', type=int, default=192, help='input batch size')
#     parser.add_argument('--saved_model', required=True, help="path to saved_model to evaluation")
#     """ Data processing """
#     parser.add_argument('--batch_max_length', type=int, default=25, help='maximum-label-length')
#     parser.add_argument('--imgH', type=int, default=32, help='the height of the input image')
#     parser.add_argument('--imgW', type=int, default=100, help='the width of the input image')
#     parser.add_argument('--rgb', action='store_true', help='use rgb input')
#     parser.add_argument('--character', type=str,
#                         default='0123456789abcdefghijklmnopqrstuvwxyz가각간갇갈감갑값갓강갖같갚갛개객걀걔거걱건걷걸검겁것겉게겨격겪견결겹경곁계고곡곤곧골곰곱곳공과관광괜괴굉교구국군굳굴굵굶굽궁권귀귓규균귤그극근글긁금급긋긍기긴길김깅깊까깍깎깐깔깜깝깡깥깨꺼꺾껌껍껏껑께껴꼬꼭꼴꼼꼽꽂꽃꽉꽤꾸꾼꿀꿈뀌끄끈끊끌끓끔끗끝끼낌나낙낚난날낡남납낫낭낮낯낱낳내냄냇냉냐냥너넉넌널넓넘넣네넥넷녀녁년념녕노녹논놀놈농높놓놔뇌뇨누눈눕뉘뉴늄느늑는늘늙능늦늬니닐님다닥닦단닫달닭닮담답닷당닿대댁댐댓더덕던덜덟덤덥덧덩덮데델도독돈돌돕돗동돼되된두둑둘둠둡둥뒤뒷드득든듣들듬듭듯등디딩딪따딱딴딸땀땅때땜떠떡떤떨떻떼또똑뚜뚫뚱뛰뜨뜩뜯뜰뜻띄라락란람랍랑랗래랜램랫략량러럭런럴럼럽럿렁렇레렉렌려력련렬렵령례로록론롬롭롯료루룩룹룻뤄류륙률륭르른름릇릎리릭린림립릿링마막만많말맑맘맙맛망맞맡맣매맥맨맵맺머먹먼멀멈멋멍멎메멘멩며면멸명몇모목몬몰몸몹못몽묘무묵묶문묻물뭄뭇뭐뭘뭣므미민믿밀밉밌및밑바박밖반받발밝밟밤밥방밭배백뱀뱃뱉버번벌범법벗베벤벨벼벽변별볍병볕보복볶본볼봄봇봉뵈뵙부북분불붉붐붓붕붙뷰브븐블비빌빔빗빚빛빠빡빨빵빼뺏뺨뻐뻔뻗뼈뼉뽑뿌뿐쁘쁨사삭산살삶삼삿상새색샌생샤서석섞선설섬섭섯성세섹센셈셋셔션소속손솔솜솟송솥쇄쇠쇼수숙순숟술숨숫숭숲쉬쉰쉽슈스슨슬슴습슷승시식신싣실싫심십싯싱싶싸싹싼쌀쌍쌓써썩썰썹쎄쏘쏟쑤쓰쓴쓸씀씌씨씩씬씹씻아악안앉않알앓암압앗앙앞애액앨야약얀얄얇양얕얗얘어억언얹얻얼엄업없엇엉엊엌엎에엔엘여역연열엷염엽엿영옆예옛오옥온올옮옳옷옹와완왕왜왠외왼요욕용우욱운울움웃웅워원월웨웬위윗유육율으윽은을음응의이익인일읽잃임입잇있잊잎자작잔잖잘잠잡잣장잦재쟁쟤저적전절젊점접젓정젖제젠젯져조족존졸좀좁종좋좌죄주죽준줄줌줍중쥐즈즉즌즐즘증지직진질짐집짓징짙짚짜짝짧째쨌쩌쩍쩐쩔쩜쪽쫓쭈쭉찌찍찢차착찬찮찰참찻창찾채책챔챙처척천철첩첫청체쳐초촉촌촛총촬최추축춘출춤춥춧충취츠측츰층치칙친칠침칫칭카칸칼캄캐캠커컨컬컴컵컷케켓켜코콘콜콤콩쾌쿄쿠퀴크큰클큼키킬타탁탄탈탑탓탕태택탤터턱턴털텅테텍텔템토톤톨톱통퇴투툴툼퉁튀튜트특튼튿틀틈티틱팀팅파팎판팔팝패팩팬퍼퍽페펜펴편펼평폐포폭폰표푸푹풀품풍퓨프플픔피픽필핏핑하학한할함합항해핵핸햄햇행향허헌험헤헬혀현혈협형혜호혹혼홀홈홉홍화확환활황회획횟횡효후훈훌훔훨휘휴흉흐흑흔흘흙흡흥흩희흰히힘?!',
#                         help='character label')
#     parser.add_argument('--sensitive', action='store_true', help='for sensitive character mode')
#     parser.add_argument('--PAD', action='store_true', help='whether to keep ratio then pad for image resize')
#     """ Model Architecture """
#     parser.add_argument('--Transformation', type=str, required=True, help='Transformation stage. None|TPS')
#     parser.add_argument('--FeatureExtraction', type=str, required=True, help='FeatureExtraction stage. VGG|RCNN|ResNet')
#     parser.add_argument('--SequenceModeling', type=str, required=True, help='SequenceModeling stage. None|BiLSTM')
#     parser.add_argument('--Prediction', type=str, required=True, help='Prediction stage. CTC|Attn')
#     parser.add_argument('--num_fiducial', type=int, default=20, help='number of fiducial points of TPS-STN')
#     parser.add_argument('--input_channel', type=int, default=1, help='the number of input channel of Feature extractor')
#     parser.add_argument('--output_channel', type=int, default=512,
#                         help='the number of output channel of Feature extractor')
#     parser.add_argument('--hidden_size', type=int, default=256, help='the size of the LSTM hidden state')
#
#     opt = parser.parse_args()
#
#     """ vocab / character number configuration """
#     if opt.sensitive:
#         opt.character = string.printable[:-6]  # same with ASTER setting (use 94 char).
#
#     cudnn.benchmark = True
#     cudnn.deterministic = True
#     opt.num_gpu = torch.cuda.device_count()
#     # print(opt.image_folder)
#     import time
#     start=time.time()
#     model=setModel(opt)
#     elapsed1=time.time()-start
#     start = time.time()
#     imgPath="./demo_image3/demo_1.jpg"
#     imgPath = "./demo_image3/demo_1.jpg"
#     demo(opt,model,imgPath)
#     elapsed2=time.time()-start
#     print(elapsed1,elapsed2)
#
# # python -m cProfile -o runTime.prof demo.py --Transformation TPS --FeatureExtraction ResNet --SequenceModeling BiLSTM --Prediction CTC --image_folder demo_image3/ --saved_model best_accuracy.pth --imgH 64 --imgW 200
#
# # python demo2.py --Transformation TPS --FeatureExtraction ResNet --SequenceModeling BiLSTM --Prediction CTC --image_folder demo_image2/ --saved_model best_accuracy.pth --imgH 64 --imgW 200
#
#
