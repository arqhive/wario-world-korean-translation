# 와리오 월드 한글 패치 v1.0f

게임큐브 **일본판 `GWWJ01`(Rev 0)**용 비공식 한글 패치입니다. 게임 이미지나 원본 게임 파일은 들어 있지 않습니다.

## 적용 방법

1. 압축을 모두 풉니다. `WarioWorld_KO_Patcher.exe`와 `patch-data.zip`은 같은 폴더에 있어야 합니다.
2. `WarioWorld_KO_Patcher.exe`를 실행합니다(Windows 64비트, 따로 설치할 것 없음).
3. 일본판 원본 **ISO 또는 GCM**을 고릅니다.
4. 결과를 저장할 경로를 정하고 **한글 패치 적용**을 누릅니다. 빈 공간이 약 1.5GB 필요합니다.
5. 완료 창이 나오면 끝입니다. 원본 이미지는 바뀌지 않습니다.

## 지원 형식

| 원본 | 결과 |
|---|---|
| ISO, GCM | ISO |
| RVZ, GCZ, CISO, NKit | 지원 안 함. Dolphin 등에서 ISO로 바꾼 뒤 적용 |

패처는 이미지 전체 해시가 아니라 디스크 안의 게임 파일을 하나하나 검사합니다. 그래서 빈 영역 채움이나 끝부분 잘림 때문에 해시가 달라진 덤프에도 적용됩니다. 북미판·유럽판, 이미 패치한 이미지, 내부 파일이 손상된 이미지에는 적용되지 않습니다.

## 명령줄

```
WarioWorld_KO_Patcher.exe --input "원본.iso" --output "한글.iso"
WarioWorld_KO_Patcher.exe --input "원본.iso" --check
```

두 번째 줄은 원본이 맞는지만 검사합니다. 같은 폴더의 `file_patcher.py`도 Python 3.11 이상에서 같은 옵션으로 쓸 수 있습니다.

## 한글화 내용

- 메뉴, 옵션, 스테이지·보물 이름, 요정 도움말, 마늘 자판기, 오프닝 이야기, 엔딩, 세이브·오류 메시지, GBA 연결 안내를 한글화했습니다.
- 목표 안내판, 타이틀 로고, 메모리 카드 배너 그림을 한글화했습니다.
- 한글과 숫자·영문·기호는 G마켓 산스 Bold로 그렸습니다.
- 원작에서도 영어인 문구(WARIO WORLD, 엔딩 크레디트 등)는 영어 그대로 두었습니다.
- GBA 연동 미니게임 안의 글씨는 한글화하지 않았습니다.

## 실행 환경

- **확인함**: Dolphin, Wii U Nintendont(USB Loader GX).

## 크레딧·라이선스

- 제작: arqhive.
- 글꼴: G마켓 산스(SIL OFL 1.1, `licenses/GmarketSans-OFL.txt`). 게임용 비트맵으로 바꿔 넣었고 글꼴 파일은 들어 있지 않습니다.
- 패처 실행 파일은 Python, Tcl/Tk, PyInstaller를 씁니다. 고지는 `licenses/`와 `THIRD_PARTY.txt`에 있습니다.

비공식 팬 번역이며 Nintendo와 관련이 없습니다. 「와리오 월드」 관련 상표·저작권은 Nintendo와 Treasure에 있습니다. 패치를 적용한 게임 파일의 배포를 금지합니다.
