# ScoreSync Modern (by UntitledCharts)
## Features
When any supported file is updated, it will be automatically updated in Sonolus as well.

Supported files include:
.sus, .usc, LevelData, .mmw, .ccmmw, .unchmmw

## Usage

1. Download release.zip from the [releases](https://github.com/Piliman22/ScoreSync/releases) page and extract it.

2. Create a new folder (with any name) inside the levels directory, and add a .sus/.usc/LevelData/.mmw/.ccmmw/.unchmmw file, a .mp3, and a .png file into it.

3. Launch `run.bat`.

4. You will see "Go to server https://~~~", open your browser it and scan the QR code with your device that has Sonolus installed to add it.

## FAQ

Q. I can't connect to the server.

A. Check your firewall settings, make sure you're on the same network, and verify the IP address. For the IP address, run `ipconfig` in Command Prompt and check if the IP address is correct. Sometimes the script may not retrieve the IP address properly depending on the device, so using the IP address from `ipconfig` may work better.

## Caution
> [!CAUTION]
> Do not touch the levels_cache folder. It will cause bugs.

## 特徴
対応しているいずれかのファイルが更新されると、
Sonolus上のデータも自動的に更新されます。

対応ファイル：
.sus、.usc、LevelData、.mmw、.ccmmw、.unchmmw

## 使い方
1. [リリース](https://github.com/Piliman22/ScoreSync/releases)から、release.zipをダウンロードし、展開してください。

2. levelsの中に新しいフォルダ（名前は自由に）を作成し、その中に
譜面ファイル（.sus / .usc / LevelData / .mmw / .ccmmw / .unchmmw のいずれか1つ）、
音声ファイル（.mp3）、画像ファイル（.png） を追加してください。

3. `run.bat`を起動してください。

4. Go to server https://~~~とあるので、それをブラウザで開き、Sonolusの入っている端末でQRコードを読み込んで開いて追加してください。

## よくある質問

Q. サーバーに入れません。

A. ファイアウォール周り、同じネットワークか、ipアドレスを見てください。ipアドレスについては、コマンドプロンプトで`ipconfig`とうち、そこでipアドレスがあってるかどうかを確認してください。端末によってはスクリプトから取得がうまく行っていない場合があるので`ipconfig`から出てきたほうのipアドレスを使うことでうまくいく場合があります

## 注意
> [!CAUTION]
> levels_cacheフォルダは基本触らないでください。バグります。