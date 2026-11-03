package cn.readingdesk.reader;

import android.app.Activity;
import android.os.Bundle;
import android.content.Intent;
import android.webkit.*;
import android.speech.tts.*;
import android.database.sqlite.SQLiteDatabase;
import android.database.Cursor;
import android.net.Uri;
import android.view.Window;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import android.media.MediaPlayer;
import android.media.PlaybackParams;
import java.security.MessageDigest;

public class MainActivity extends Activity {
    WebView web;
    TextToSpeech tts;
    volatile boolean ttsReady=false;
    volatile boolean paused=false;
    volatile String spokenText="", utterance="";
    volatile int speechOffset=0, baseOffset=0, chunkEnd=0;
    ExecutorService executor=Executors.newFixedThreadPool(4);
    SQLiteDatabase dictionary;
    String pendingCsv, pendingBackup;
    String pendingFileRequest="";
    volatile String speechTag="";
    MediaPlayer wordPlayer;
    AtomicInteger audioGeneration=new AtomicInteger();
    volatile boolean destroyed=false;
    boolean onlinePaused=false;
    volatile String lastEndpoint="",lastToken="";
    volatile long googleOkUntil=0;
    boolean googleHot(){return System.currentTimeMillis()<googleOkUntil;}
    void markGoogleOk(){googleOkUntil=System.currentTimeMillis()+600000;}


    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setStatusBarColor(0xfff4f6fa);
        getWindow().setNavigationBarColor(0xfff4f6fa);
        web=new WebView(this);
        android.widget.FrameLayout frame=new android.widget.FrameLayout(this);
        frame.addView(web,new android.widget.FrameLayout.LayoutParams(-1,-1));
        setContentView(frame);
        getWindow().getDecorView().setSystemUiVisibility(android.view.View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
        if(android.os.Build.VERSION.SDK_INT>=30){
            getWindow().setDecorFitsSystemWindows(false);
            frame.setOnApplyWindowInsetsListener((view,insets)->{
                android.graphics.Insets bars=insets.getInsets(android.view.WindowInsets.Type.systemBars());
                view.setPadding(bars.left,bars.top,bars.right,bars.bottom);
                return android.view.WindowInsets.CONSUMED;
            });
        }
        web.setWebChromeClient(new WebChromeClient());
        WebSettings settings=web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setTextZoom(100);
        web.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request){return true;}
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request){
                if (!request.getUrl().toString().startsWith("file:///android_asset/"))
                    return new WebResourceResponse("text/plain","utf-8",new ByteArrayInputStream(new byte[0]));
                return null;
            }
        });
        web.addJavascriptInterface(new Bridge(),"ReaderNative");
        tts=new TextToSpeech(this,status->{
            if(status==TextToSpeech.SUCCESS){
                int language=tts.setLanguage(Locale.US);
                ttsReady=language!=TextToSpeech.LANG_MISSING_DATA && language!=TextToSpeech.LANG_NOT_SUPPORTED;
                tts.setSpeechRate(0.9f);
                tts.setOnUtteranceProgressListener(new UtteranceProgressListener(){
                    public void onStart(String id){}
                    public void onDone(String id){if(id.equals(utterance)){if(chunkEnd<spokenText.length()){speechOffset=chunkEnd;runOnUiThread(()->speakFromOffset());}else{speechOffset=0;paused=false;if(speechTag.isEmpty())notice("朗读完成");speechDone("");}}}
                    public void onError(String id){if(id.equals(utterance)){notice("朗读失败，请检查手机英文语音设置");speechDone("朗读失败，请检查英文语音设置");}}
                    @Override public void onRangeStart(String id,int start,int end,int frame){if(id.equals(utterance))speechOffset=baseOffset+start;}
                });
            }
        });
        executor.execute(()->{
            try {
                File file=new File(getFilesDir(),"dictionary.sqlite3");
                if(!file.exists()){
                    File staging=new File(getFilesDir(),"dictionary.tmp");
                    try(InputStream input=getAssets().open("dictionary.sqlite3");OutputStream output=new FileOutputStream(staging)){
                        byte[] buffer=new byte[65536];int read;while((read=input.read(buffer))!=-1)output.write(buffer,0,read);
                    }
                    if(!staging.renameTo(file))throw new IOException("词库安装失败");
                }
                dictionary=SQLiteDatabase.openDatabase(file.getPath(),null,SQLiteDatabase.OPEN_READONLY);
            } catch(Exception error){notice("本地词库尚不可用，可继续尝试在线翻译");}
        });
        web.loadUrl("file:///android_asset/index.html");
    }

    void speechDone(String error){
        final String tag=speechTag;
        if(tag.isEmpty())return;
        speechTag="";
        runOnUiThread(()->{if(web!=null)web.evaluateJavascript("window.nativeSpeechDone&&window.nativeSpeechDone("+JSONObject.quote(tag)+","+JSONObject.quote(error)+")",null);});
    }
    void notice(String message){
        if(web!=null)runOnUiThread(()->web.evaluateJavascript("window.nativeNotice&&window.nativeNotice("+JSONObject.quote(message)+")",null));
    }
    void reply(String id,JSONObject result){
        runOnUiThread(()->{if(web!=null)web.evaluateJavascript("window.nativeReply("+JSONObject.quote(id)+","+result.toString()+")",null);});
    }
    JSONObject request(String endpoint,String path,JSONObject payload,String token)throws Exception{
        URI uri=new URI(endpoint);
        String host=uri.getHost();int port=uri.getPort();
        if(!"http".equals(uri.getScheme())||host==null||!host.matches("[0-9.]+")||uri.getRawUserInfo()!=null||uri.getQuery()!=null||uri.getFragment()!=null||!(uri.getPath().isEmpty()||"/".equals(uri.getPath()))||port<1||port>65535)
            throw new IOException("请填写电脑显示的地址，例如 http://192.168.1.10:18765");
        InetAddress address=InetAddress.getByName(host);
        if(!address.isSiteLocalAddress()&&!address.isLoopbackAddress())throw new IOException("仅允许连接局域网电脑地址");
        HttpURLConnection connection=(HttpURLConnection)new URL("http://"+host+":"+port+path).openConnection();
        connection.setConnectTimeout(4000);connection.setReadTimeout(path.equals("/translate")?20000:10000);
        connection.setInstanceFollowRedirects(false);connection.setRequestMethod("POST");connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type","application/json; charset=utf-8");
        if(!token.isEmpty())connection.setRequestProperty("Authorization","Bearer "+token);
        try{
            byte[] bytes=payload.toString().getBytes(StandardCharsets.UTF_8);
            connection.setFixedLengthStreamingMode(bytes.length);
            try(OutputStream out=connection.getOutputStream()){out.write(bytes);}
            int code=connection.getResponseCode();
            InputStream input=code>=200&&code<300?connection.getInputStream():connection.getErrorStream();
            if(input==null)throw new IOException("电脑未响应，请检查同步服务与网络");
            String body=readAll(input,5000000);
            JSONObject result=new JSONObject(body);
            if(code<200||code>=300)throw new IOException(result.optString("error","同步失败"));
            return result;
        }finally{connection.disconnect();}
    }
    String readAll(InputStream input,int limit)throws IOException{
        try(InputStream in=input;ByteArrayOutputStream out=new ByteArrayOutputStream()){
            byte[] buffer=new byte[8192];int n;while((n=in.read(buffer))!=-1){out.write(buffer,0,n);if(out.size()>limit)throw new IOException("数据过大，请分批导入");}
            return out.toString("UTF-8");
        }
    }
    String dictionaryLookup(String text){
        if(dictionary==null||text.length()>100)return null;
        try(Cursor cursor=dictionary.rawQuery("SELECT meaning FROM words WHERE word=?",new String[]{text.toLowerCase(Locale.ROOT)})){
            return cursor.moveToFirst()?cursor.getString(0):null;
        }
    }
    String translate(String text)throws Exception{
        String local=dictionaryLookup(text);if(local!=null)return local;
        String[] parts=text.split("(?<=\\s)");StringBuilder chunk=new StringBuilder(),all=new StringBuilder();
        for(String part:parts){
            if(chunk.length()+part.length()>400&&chunk.length()>0){all.append(translateChunk(chunk.toString())).append("\n");chunk.setLength(0);}
            chunk.append(part);
        }
        if(chunk.length()>0)all.append(translateChunk(chunk.toString()));
        return all.toString().trim();
    }
    String translateChunk(String text)throws Exception{
        if(text.length()>1000)throw new IOException("请选取较短的英文片段后重试");
        String query=URLEncoder.encode(text,"UTF-8");
        HttpURLConnection connection=(HttpURLConnection)new URL("https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q="+query).openConnection();
        connection.setConnectTimeout(4000);connection.setReadTimeout(5000);connection.setRequestProperty("User-Agent","ReadingDesk/1.0");
        try{
            JSONArray data=new JSONArray(readAll(connection.getInputStream(),200000));JSONArray segments=data.getJSONArray(0);StringBuilder result=new StringBuilder();
            for(int i=0;i<segments.length();i++)result.append(segments.getJSONArray(i).optString(0,""));
            if(result.length()==0)throw new IOException("翻译未返回结果");return result.toString();
        }finally{connection.disconnect();}
    }
    boolean isSingleWord(String text){return text.length()<=80&&text.matches("[A-Za-z]+(?:['’\\-][A-Za-z]+)*");}
    void releaseWordPlayer(){
        if(wordPlayer!=null){try{wordPlayer.release();}catch(Exception ignored){}wordPlayer=null;}
    }
    void stopAudio(){
        audioGeneration.incrementAndGet();utterance="stopped";speechTag="";
        releaseWordPlayer();tts.stop();paused=false;onlinePaused=false;speechOffset=0;
    }
    void speakSystem(String text,String accent,double speed){
        Locale wanted=accent.equals("uk")?Locale.UK:Locale.US;
        int language=tts.setLanguage(wanted);
        if(language==TextToSpeech.LANG_MISSING_DATA||language==TextToSpeech.LANG_NOT_SUPPORTED)
            language=tts.setLanguage(Locale.US);
        ttsReady=language!=TextToSpeech.LANG_MISSING_DATA&&language!=TextToSpeech.LANG_NOT_SUPPORTED;
        tts.setSpeechRate((float)speed);say(text);
    }
    void startSpeech(String text,String accent,double speed,String source,String requestTag){
        stopAudio();speechTag=requestTag;final int generation=audioGeneration.get();
        if(source.equals("dictionary")){
            java.util.List<String> chunks=isSingleWord(text)?java.util.Collections.singletonList(text):SpeechChunks.split(text);
            playOnlineChunk(chunks,0,accent,speed,generation,isSingleWord(text));
        }else speakSystem(text,accent,speed);
    }
    void playOnlineChunk(java.util.List<String> chunks,int index,String accent,double speed,int generation,boolean single){
        if(destroyed||generation!=audioGeneration.get())return;
        if(index>=chunks.size()){speechDone("");return;}
        String text=chunks.get(index);
        notice(single?"正在载入词典发音…":"正在载入在线整句语音…");
        executor.execute(()->{
            try{
                File file=pronunciationFile(text,accent,single);
                runOnUiThread(()->{
                    if(destroyed||generation!=audioGeneration.get())return;
                    MediaPlayer player=new MediaPlayer();wordPlayer=player;
                    try{
                        player.setAudioAttributes(new android.media.AudioAttributes.Builder().setUsage(android.media.AudioAttributes.USAGE_MEDIA).setContentType(android.media.AudioAttributes.CONTENT_TYPE_SPEECH).build());
                        player.setDataSource(file.getPath());
                        player.setOnPreparedListener(mp->{
                            if(generation!=audioGeneration.get()||wordPlayer!=mp)return;
                            try{mp.setPlaybackParams(new PlaybackParams().setSpeed((float)speed).setPitch(1.0f));if(onlinePaused)mp.pause();else mp.start();notice(onlinePaused?"已暂停":(single?"词典发音":"在线整句朗读")+" · "+speed+" 倍速");}
                            catch(Exception error){fallbackOnline(chunks,index,accent,speed,generation);}
                        });
                        player.setOnCompletionListener(mp->{
                            if(generation!=audioGeneration.get()||wordPlayer!=mp)return;
                            releaseWordPlayer();playOnlineChunk(chunks,index+1,accent,speed,generation,single);
                        });
                        player.setOnErrorListener((mp,what,extra)->{if(wordPlayer==mp)fallbackOnline(chunks,index,accent,speed,generation);return true;});
                        player.prepareAsync();
                    }catch(Exception error){fallbackOnline(chunks,index,accent,speed,generation);}
                });
            }catch(Exception error){runOnUiThread(()->fallbackOnline(chunks,index,accent,speed,generation));}
        });
    }
    void fallbackOnline(java.util.List<String> chunks,int index,String accent,double speed,int generation){
        if(destroyed||generation!=audioGeneration.get())return;
        if(onlinePaused){new android.os.Handler(android.os.Looper.getMainLooper()).postDelayed(()->fallbackOnline(chunks,index,accent,speed,generation),200);return;}
        releaseWordPlayer();notice("在线音频不可用，剩余内容改用系统语音");
        speakSystem(android.text.TextUtils.join(" ",chunks.subList(index,chunks.size())),accent,speed);
    }
    File pronunciationFile(String text,String accent,boolean single)throws Exception{
        String word=text.replace('’','\'');
        if(single&&!(word.length()>1&&word.matches("[A-Z]+")))word=word.toLowerCase(Locale.ROOT);
        byte[] hash=MessageDigest.getInstance("SHA-256").digest(((single?"word:":"sentence:")+accent+":"+word).getBytes(StandardCharsets.UTF_8));
        StringBuilder name=new StringBuilder();for(byte b:hash)name.append(String.format(Locale.ROOT,"%02x",b&255));
        File folder=new File(getFilesDir(),"pronunciation");if(!folder.exists())folder.mkdirs();
        File target=new File(folder,name.toString()+".mp3");
        if(target.isFile()&&target.length()>=128)return target;
        if(single){
            writeCachedFile(target,downloadAudio("https://dict.youdao.com/dictvoice?audio="+URLEncoder.encode(word,"UTF-8")+"&type="+(accent.equals("uk")?"1":"2")));
            return target;
        }
        // Sentences: try whichever online path proved working — Google direct (needs VPN/overseas) or the desktop relay (needs the PC on).
        Exception last=null;boolean googleTried=false;
        String google="https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl="+(accent.equals("uk")?"en-GB":"en-US")+"&q="+URLEncoder.encode(word,"UTF-8");
        if(googleHot()){
            googleTried=true;
            try{writeCachedFile(target,downloadAudio(google));markGoogleOk();return target;}
            catch(Exception error){last=error;googleOkUntil=0;}
        }
        if(!lastEndpoint.isEmpty()){
            try{writeCachedFile(target,postDesktopTts(word,accent));return target;}
            catch(Exception error){last=error;}
        }
        if(!googleTried){
            try{writeCachedFile(target,downloadAudio(google));markGoogleOk();return target;}
            catch(Exception error){last=error;}
        }
        throw last==null?new IOException("发音服务暂不可用"):last;
    }
    void writeCachedFile(File target,byte[] data)throws IOException{
        File temporary=File.createTempFile("voice-",".tmp",target.getParentFile());
        try{
            try(FileOutputStream file=new FileOutputStream(temporary)){file.write(data);}
            if(!temporary.renameTo(target)&&!target.isFile())throw new IOException("缓存失败");
        }finally{temporary.delete();}
    }
    byte[] postDesktopTts(String text,String accent)throws Exception{
        URI uri=new URI(lastEndpoint);
        String host=uri.getHost();int port=uri.getPort();
        if(!"http".equals(uri.getScheme())||host==null||port<1||port>65535)throw new IOException("电脑地址无效");
        JSONObject body=new JSONObject();body.put("text",text);body.put("accent",accent);
        HttpURLConnection connection=(HttpURLConnection)new URL("http://"+host+":"+port+"/tts").openConnection();
        connection.setConnectTimeout(4000);connection.setReadTimeout(15000);connection.setRequestMethod("POST");connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type","application/json; charset=utf-8");
        if(!lastToken.isEmpty())connection.setRequestProperty("Authorization","Bearer "+lastToken);
        try{
            byte[] bytes=body.toString().getBytes(StandardCharsets.UTF_8);
            connection.setFixedLengthStreamingMode(bytes.length);
            try(OutputStream out=connection.getOutputStream()){out.write(bytes);}
            int code=connection.getResponseCode();
            if(code<200||code>=300)throw new IOException("电脑语音服务返回 "+code);
            ByteArrayOutputStream output=new ByteArrayOutputStream();
            try(InputStream input=connection.getInputStream()){
                byte[] buffer=new byte[8192];int count;
                while((count=input.read(buffer))!=-1){output.write(buffer,0,count);if(output.size()>512000)throw new IOException("音频过大");}
            }
            byte[] data=output.toByteArray();
            boolean mp3=data.length>=128&&((data[0]=='I'&&data[1]=='D'&&data[2]=='3')||((data[0]&255)==255&&(data[1]&224)==224));
            if(!mp3)throw new IOException("音频内容无效");
            return data;
        }finally{connection.disconnect();}
    }
    byte[] downloadAudio(String url)throws IOException{
        HttpURLConnection connection=(HttpURLConnection)new URL(url).openConnection();
        connection.setConnectTimeout(4000);connection.setReadTimeout(5000);connection.setRequestProperty("User-Agent","Mozilla/5.0 ReadingDesk/1.1");
        try{
            ByteArrayOutputStream output=new ByteArrayOutputStream();
            try(InputStream input=connection.getInputStream()){
                byte[] buffer=new byte[8192];int count;
                while((count=input.read(buffer))!=-1){output.write(buffer,0,count);if(output.size()>512000)throw new IOException("音频过大");}
            }
            byte[] data=output.toByteArray();
            boolean mp3=data.length>=128&&((data[0]=='I'&&data[1]=='D'&&data[2]=='3')||((data[0]&255)==255&&(data[1]&224)==224));
            if(!mp3)throw new IOException("音频内容无效");
            return data;
        }finally{connection.disconnect();}
    }
    void say(String text){
        if(!ttsReady){notice("未找到英文语音，请在手机系统的文字转语音设置中下载英语语音包");speechDone("未找到英文语音，请先下载英语语音包");return;}
        tts.stop();spokenText=text;speechOffset=0;baseOffset=0;paused=false;
        utterance="speech-"+System.nanoTime();
        // System engines usually limit one utterance to 4000 characters.
        speakFromOffset();
    }
    void speakFromOffset(){
        String text=spokenText.substring(Math.min(speechOffset,spokenText.length()));
        baseOffset=speechOffset;
        if(text.length()>TextToSpeech.getMaxSpeechInputLength())text=text.substring(0,TextToSpeech.getMaxSpeechInputLength());
        if(!text.isEmpty()&&Character.isHighSurrogate(text.charAt(text.length()-1)))text=text.substring(0,text.length()-1);
        chunkEnd=baseOffset+text.length();
        tts.speak(text,TextToSpeech.QUEUE_FLUSH,null,utterance);
    }
    public class Bridge{
        @JavascriptInterface public void send(String id,String action,String raw){
            executor.execute(()->{
                JSONObject response=new JSONObject();
                try{
                    JSONObject p=new JSONObject(raw);
                    if(action.equals("pair")||action.equals("sync")){
                        response=request(p.getString("url"),action.equals("pair")?"/pair":"/sync",p.getJSONObject("body"),p.optString("token",""));
                        lastEndpoint=p.getString("url");
                        String issued=p.optString("token","");if(issued.isEmpty())issued=response.optString("token","");if(!issued.isEmpty())lastToken=issued;
                    }else if(action.equals("translate")){
                        String text=p.getString("text").trim();if(text.isEmpty()||text.length()>20000)throw new IOException("请选择 20000 字符以内的英文内容");
                        String local=dictionaryLookup(text);
                        if(local!=null)response.put("text",local);
                        else{
                            // Adaptive: whichever online path proved working (Google direct needs VPN, desktop needs the PC on) is tried first for 10 minutes.
                            Exception last=null;boolean desktopTried=false;
                            String url=p.optString("url");String token=p.optString("token");
                            if(!googleHot()&&!url.isEmpty()){
                                desktopTried=true;
                                try{JSONObject body=new JSONObject();body.put("text",text);
                                    response=request(url,"/translate",body,token);
                                    lastEndpoint=url;if(!token.isEmpty())lastToken=token;
                                }catch(Exception error){last=error;}
                            }
                            if(!response.has("text")){
                                try{response.put("text",translate(text));markGoogleOk();}
                                catch(Exception error){last=error;googleOkUntil=0;}
                            }
                            if(!response.has("text")&&!desktopTried&&!url.isEmpty()){
                                try{JSONObject body=new JSONObject();body.put("text",text);
                                    response=request(url,"/translate",body,token);
                                    lastEndpoint=url;if(!token.isEmpty())lastToken=token;
                                }catch(Exception error){last=error;}
                            }
                            if(!response.has("text")&&last!=null)throw last;
                        }
                    }else if(action.equals("speak")){
                        String text=p.getString("text").trim();
                        String accent=p.optString("accent","us").equals("uk")?"uk":"us";
                        double speed=Math.max(0.6,Math.min(1.0,p.optDouble("speed",0.75)));
                        String source=p.optString("source","dictionary").equals("system")?"system":"dictionary";
                        String requestTag=p.optString("request_id","");
                        runOnUiThread(()->startSpeech(text,accent,speed,source,requestTag));response.put("ok",true);
                    }else if(action.equals("pause")){
                        runOnUiThread(()->{onlinePaused=!onlinePaused;if(wordPlayer!=null){try{if(wordPlayer.isPlaying()){wordPlayer.pause();notice("已暂停");}else{wordPlayer.start();notice("继续发音");}}catch(Exception ignored){}return;}if(paused){paused=false;utterance="speech-"+System.nanoTime();speakFromOffset();notice("继续朗读");}else if(tts.isSpeaking()){paused=true;utterance="paused";tts.stop();notice("已暂停");}});response.put("ok",true);
                    }else if(action.equals("stop")){runOnUiThread(()->stopAudio());response.put("ok",true);
                    }else if(action.equals("chooseBackground")||action.equals("importBackup")){
                        if(!pendingFileRequest.isEmpty())throw new IOException("已有文件选择窗口，请先完成或取消");
                        pendingFileRequest=id;
                        runOnUiThread(()->{
                            try{
                                Intent intent=new Intent(Intent.ACTION_OPEN_DOCUMENT);intent.addCategory(Intent.CATEGORY_OPENABLE);
                                intent.setType(action.equals("chooseBackground")?"image/*":"application/json");
                                startActivityForResult(intent,action.equals("chooseBackground")?43:44);
                            }catch(Exception error){String waiting=pendingFileRequest;pendingFileRequest="";JSONObject failure=new JSONObject();try{failure.put("error","无法打开文件选择器");}catch(Exception ignored){}reply(waiting,failure);}
                        });
                        return;
                    }else if(action.equals("exportBackup")){
                        pendingBackup=p.getString("data");if(pendingBackup.length()>15000000)throw new IOException("备份过大，请先移除过大的背景图");
                        runOnUiThread(()->{Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);intent.addCategory(Intent.CATEGORY_OPENABLE);intent.setType("application/json");intent.putExtra(Intent.EXTRA_TITLE,"ReadingDesk-"+System.currentTimeMillis()+".json");startActivityForResult(intent,45);});response.put("ok",true);
                    }else if(action.equals("export")){
                        pendingCsv=p.getString("csv");runOnUiThread(()->{Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);intent.addCategory(Intent.CATEGORY_OPENABLE);intent.setType("text/csv");intent.putExtra(Intent.EXTRA_TITLE,"英语生词表.csv");startActivityForResult(intent,42);});response.put("ok",true);
                    }else throw new IOException("不支持的操作");
                }catch(Exception error){try{response.put("error",error instanceof IOException?error.getMessage():"操作失败，请检查网络或重试");}catch(JSONException ignored){}}
                reply(id,response);
            });
        }
    }
    @Override protected void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request,result,data);
        if(request==43||request==44){
            final String waiting=pendingFileRequest;pendingFileRequest="";
            if(result!=RESULT_OK||data==null||data.getData()==null){JSONObject cancelled=new JSONObject();try{cancelled.put("cancelled",true);}catch(Exception ignored){}reply(waiting,cancelled);return;}
            final Uri uri=data.getData();
            executor.execute(()->{
                JSONObject response=new JSONObject();
                try{
                    if(request==44){
                        try(InputStream input=getContentResolver().openInputStream(uri)){response.put("data",readAll(input,15000000));}
                    }else{
                        android.graphics.BitmapFactory.Options bounds=new android.graphics.BitmapFactory.Options();bounds.inJustDecodeBounds=true;
                        try(InputStream input=getContentResolver().openInputStream(uri)){android.graphics.BitmapFactory.decodeStream(input,null,bounds);}
                        if(bounds.outWidth<=0||bounds.outHeight<=0)throw new IOException("图片无法读取");
                        int sample=1;while(Math.max(bounds.outWidth,bounds.outHeight)/sample>1600)sample*=2;
                        android.graphics.BitmapFactory.Options options=new android.graphics.BitmapFactory.Options();options.inSampleSize=sample;
                        android.graphics.Bitmap image;
                        try(InputStream input=getContentResolver().openInputStream(uri)){image=android.graphics.BitmapFactory.decodeStream(input,null,options);}
                        if(image==null)throw new IOException("图片无法读取");
                        ByteArrayOutputStream bytes=new ByteArrayOutputStream();image.compress(android.graphics.Bitmap.CompressFormat.JPEG,78,bytes);image.recycle();
                        if(bytes.size()>900000)throw new IOException("图片过大，请选择较小的图片");
                        response.put("image","data:image/jpeg;base64,"+android.util.Base64.encodeToString(bytes.toByteArray(),android.util.Base64.NO_WRAP));
                    }
                }catch(Exception error){try{response.put("error",error instanceof IOException?error.getMessage():"文件无法读取");}catch(Exception ignored){}}
                reply(waiting,response);
            });return;
        }
        if(request==45&&result==RESULT_OK&&data!=null&&data.getData()!=null){
            try(OutputStream output=getContentResolver().openOutputStream(data.getData())){output.write(pendingBackup.getBytes(StandardCharsets.UTF_8));notice("完整备份文件已导出");}
            catch(Exception error){notice("备份导出失败，请重新选择位置");}
            pendingBackup=null;return;
        }
        if(request==42&&result==RESULT_OK&&data!=null&&data.getData()!=null){
            try(OutputStream output=getContentResolver().openOutputStream(data.getData())){
                output.write(("\ufeff"+pendingCsv).getBytes(StandardCharsets.UTF_8));notice("CSV 已导出");
            }catch(Exception error){notice("导出失败，请重新选择保存位置");}
        }
    }
    @Override public void onBackPressed(){web.evaluateJavascript("window.handleBack()",null);}
    @Override protected void onDestroy(){
        destroyed=true;audioGeneration.incrementAndGet();releaseWordPlayer();
        if(tts!=null){tts.stop();tts.shutdown();}executor.shutdownNow();
        if(dictionary!=null)dictionary.close();if(web!=null){web.removeJavascriptInterface("ReaderNative");web.destroy();web=null;}
        super.onDestroy();
    }
}
