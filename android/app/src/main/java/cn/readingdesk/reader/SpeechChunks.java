package cn.readingdesk.reader;
import java.util.ArrayList;
import java.util.List;
final class SpeechChunks {
 static List<String> split(String input) {
  List<String> chunks=new ArrayList<>();String text=input.trim();
  while(!text.isEmpty()) {
   int end=Math.min(180,text.length());
   if(end<text.length()) {
    int boundary=-1;
    for(int i=0;i<end;i++)if(Character.isWhitespace(text.charAt(i)))boundary=i;
    if(boundary>0)end=boundary;
    if(Character.isHighSurrogate(text.charAt(end-1)))end--;
   }
   chunks.add(text.substring(0,end));text=text.substring(end).trim();
  }
  return chunks;
 }
}
