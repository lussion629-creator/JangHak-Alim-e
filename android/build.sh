#!/usr/bin/env bash
# 장학알리미 APK 빌드 (Gradle 없이 aapt2 + javac + d8 + apksigner)
# 필요: JDK 17+, aapt2, android.jar(API 35), d8.jar, apksigner.jar  → TOOLS 디렉터리에 두기
set -euo pipefail
cd "$(dirname "$0")"
TOOLS=${TOOLS:-./tools}
AAPT2=${AAPT2:-$TOOLS/aapt2}
ANDROID_JAR=$TOOLS/android.jar
VERSION=${VERSION:-1.0.0}
OUT=build; rm -rf $OUT; mkdir -p $OUT/res $OUT/classes $OUT/assets/www
# 1) 웹앱을 assets/www 로 (문서 머리말 포함)
python3 ../scripts/build_site.py >/dev/null
cp -r ../site/. $OUT/assets/www/ && rm -f $OUT/assets/www/data/*.gz
# 2) 리소스 컴파일·링크
$AAPT2 compile --dir res -o $OUT/res.zip
$AAPT2 link -o $OUT/base.apk -I $ANDROID_JAR --manifest AndroidManifest.xml -A $OUT/assets $OUT/res.zip \
  --min-sdk-version 24 --target-sdk-version 35 --version-name "$VERSION" -0 json
# 3) 자바 → dex
javac -source 8 -target 8 -bootclasspath $ANDROID_JAR -classpath $ANDROID_JAR -d $OUT/classes -nowarn -Xlint:-options $(find src -name '*.java')
java -cp $TOOLS/d8.jar com.android.tools.r8.D8 --release --min-api 24 --lib $ANDROID_JAR --output $OUT $(find $OUT/classes -name '*.class')
# 4) dex 추가 + 4바이트 정렬
python3 zipalign.py $OUT/base.apk $OUT/classes.dex $OUT/aligned.apk
# 5) 서명 (같은 키로 서명해야 업데이트 설치가 됨)
# 서명 키와 비밀번호는 저장소에 넣지 않는다: KEYSTORE / KEYSTORE_PASS 환경 변수로만 받는다
KEYSTORE=${KEYSTORE:-release.jks}
: "${KEYSTORE_PASS:?KEYSTORE_PASS 환경 변수를 설정하세요 (서명 키 비밀번호)}"
[ -f "$KEYSTORE" ] || keytool -genkeypair -keystore "$KEYSTORE" -storepass "$KEYSTORE_PASS" -keypass "$KEYSTORE_PASS" -alias jangak \
  -keyalg RSA -keysize 3072 -validity 10000 -dname "CN=Jangak Alimi, O=IVF, C=KR"
java -jar $TOOLS/apksigner.jar sign --ks "$KEYSTORE" --ks-pass env:KEYSTORE_PASS --key-pass env:KEYSTORE_PASS \
  --min-sdk-version 24 --out ../jangak-alimi-$VERSION.apk $OUT/aligned.apk
java -jar $TOOLS/apksigner.jar verify --verbose ../jangak-alimi-$VERSION.apk | head -5
echo "완료: jangak-alimi-$VERSION.apk"
