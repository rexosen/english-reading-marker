package cn.readingdesk.reader;
public class SpeechChunksTest {
 public static void main(String[] args) {
  check(SpeechChunks.split("   ").isEmpty());
  check(SpeechChunks.split("Hello world.").get(0).equals("Hello world."));
  StringBuilder s=new StringBuilder();for(int i=0;i<200;i++)s.append("English sentence. ");
  String text=s.toString().trim();String joined=String.join(" ",SpeechChunks.split(text));check(joined.equals(text));
  for(String c:SpeechChunks.split(text))check(c.length()<=180);
  StringBuilder longWord=new StringBuilder();for(int i=0;i<400;i++)longWord.append("a");
  check(String.join("",SpeechChunks.split(longWord.toString())).equals(longWord.toString()));
  check(SpeechChunks.split("Hello 😀 world.").get(0).equals("Hello 😀 world."));
  System.out.println("Speech chunk tests passed");
 }
 static void check(boolean b){if(!b)throw new AssertionError();}
}
