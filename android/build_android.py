"""Build a signed APK using official Android SDK tools and the local JDK 17."""
from pathlib import Path
import argparse,os,secrets,shutil,subprocess,zipfile,ctypes
root=Path(__file__).resolve().parent.parent
buffer=ctypes.create_unicode_buffer(4096)
if ctypes.windll.kernel32.GetShortPathNameW(str(root),buffer,4096):root=Path(buffer.value)
parser=argparse.ArgumentParser()
parser.add_argument('--output',required=True)
parser.add_argument('--jdk',default=r'D:\JavaWeb202309\jdk-17.0.9')
args=parser.parse_args()
jdk=Path(args.jdk)
sdk=root/'work/android-sdk'
tools=sdk/'build-tools/android-15'
androidjar=sdk/'platforms/android-35/android.jar'
work=root/'work/android-build'
for folder in ['classes','dex','generated']:(work/folder).mkdir(parents=True,exist_ok=True)
assets=root/'android/app/src/main/assets'
shutil.copy2(root/'assets/dictionary.sqlite3',assets/'dictionary.sqlite3')
shutil.copy2(root/'assets/ECDICT-LICENSE.txt',assets/'ECDICT-LICENSE.txt')
icon=root/'assets/reading-icon.png'
shutil.copy2(icon,root/'android/app/src/main/res/drawable/icon.png')
java=jdk/'bin/java.exe'
env=os.environ.copy();env['JAVA_HOME']=str(jdk)
def run(*command):
    subprocess.run([str(x) for x in command],check=True,cwd=root,env=env)
run(tools/'aapt2.exe','compile','--dir',root/'android/app/src/main/res','-o',work/'compiled.zip')
run(tools/'aapt2.exe','link','-o',work/'resources.apk','-I',androidjar,'--manifest',root/'android/app/src/main/AndroidManifest.xml','--java',work/'generated','-A',assets,'-R',work/'compiled.zip','--auto-add-overlay')
source=root/'android/app/src/main/java/cn/readingdesk/reader/MainActivity.java'
run(jdk/'bin/javac.exe','-encoding','UTF-8','--release','8','-classpath',androidjar,'-d',work/'classes',*list(source.parent.glob('*.java')),*list((work/'generated').rglob('*.java')))
with zipfile.ZipFile(work/'classes.jar','w') as archive:
    for path in (work/'classes').rglob('*.class'):archive.write(path,path.relative_to(work/'classes'))
run(java,'-cp',tools/'lib/d8.jar','com.android.tools.r8.D8','--lib',androidjar,'--min-api','26','--output',work/'dex',work/'classes.jar')
shutil.copy2(work/'resources.apk',work/'unsigned.apk')
with zipfile.ZipFile(work/'unsigned.apk','a',zipfile.ZIP_DEFLATED) as archive:archive.write(work/'dex/classes.dex','classes.dex')
run(tools/'zipalign.exe','-f','4',work/'unsigned.apk',work/'aligned.apk')
signing=root/'work/android-signing';signing.mkdir(exist_ok=True)
password=signing/'password.txt';keystore=signing/'readingdesk.p12'
if not password.exists():password.write_text(secrets.token_urlsafe(32),encoding='utf-8')
if not keystore.exists():
    run(jdk/'bin/keytool.exe','-genkeypair','-keystore',keystore,'-storetype','PKCS12','-alias','readingdesk','-keyalg','RSA','-keysize','3072','-validity','10000','-dname','CN=ReadingDesk,OU=Personal Reader,O=ReadingDesk,C=CN','-storepass:file',password,'-keypass:file',password)
output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
run(java,'-jar',tools/'lib/apksigner.jar','sign','--ks',keystore,'--ks-key-alias','readingdesk','--ks-pass','file:'+str(password),'--out',output,work/'aligned.apk')
run(java,'-jar',tools/'lib/apksigner.jar','verify','--verbose',output)
print('APK ready:',output,'bytes:',output.stat().st_size)
