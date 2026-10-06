; Headless runtime harness (InitializeSetup returns False: no window is ever shown).
; Decodes the 24 book frames at 250% through every candidate path inside the 32-bit Setup process,
; times it, records memory, and writes BMPs + results.txt next to the exe.
#ifndef Tag
  #define Tag "run"
#endif
[Setup]
AppName=AnimDecodeHarness
AppVersion=1.0
CreateAppDir=no
Uninstallable=no
PrivilegesRequired=lowest
OutputDir=out
OutputBaseFilename=rt_harness
Compression=lzma
SolidCompression=yes
ArchitecturesAllowed=x64compatible or arm64
SetupLogging=yes

[Files]
Source: "otzwebp.dll"; Flags: dontcopy
Source: "frames\A_*.jxr"; Flags: dontcopy nocompression
Source: "frames\B_*.jxr"; Flags: dontcopy nocompression
Source: "frames\W_*.webp"; Flags: dontcopy nocompression
Source: "frames\P_*.png"; Flags: dontcopy nocompression

[Code]
const
  CLSID_WICImagingFactory = '{CACAF262-9370-4615-A13B-9F5539DA4C0A}';
  WICPixelFormat32bppBGRA = '{6FDDC324-4E03-4BFE-B185-3D77768DC90F}';
  WICPixelFormat32bppPBGRA = '{6FDDC324-4E03-4BFE-B185-3D77768DC910}';

type
  IWICBitmapSource = interface(IUnknown)
    '{00000120-A8F2-4877-BA0A-FD2B6645FB94}'
    function GetSize(var Width, Height: Cardinal): HResult;
    procedure GetPixelFormat;
    procedure GetResolution;
    procedure CopyPalette;
    function CopyPixels(Rect: Cardinal; Stride, BufferSize, Buffer: Cardinal): HResult;
  end;

  IWICFormatConverter = interface(IWICBitmapSource)
    '{00000301-A8F2-4877-BA0A-FD2B6645FB94}'
    function Initialize(Source: IWICBitmapSource; var DstFormat: TGUID; Dither: Integer;
      Palette: Cardinal; AlphaThresholdPercent: Double; PaletteTranslate: Integer): HResult;
  end;

  IWICBitmapDecoder = interface(IUnknown)
    '{9EDDE9E7-8DEE-47EA-99DF-E6FAF2ED44BF}'
    procedure QueryCapability;
    procedure Initialize;
    procedure GetContainerFormat;
    procedure GetDecoderInfo;
    procedure CopyPalette;
    procedure GetMetadataQueryReader;
    procedure GetPreview;
    procedure GetColorContexts;
    procedure GetThumbnail;
    procedure GetFrameCount;
    function GetFrame(Index: Cardinal; out Frame: IUnknown): HResult;
  end;

  IWICImagingFactory = interface(IUnknown)
    '{EC5EC8A9-C395-4314-9C77-54D7A935FF70}'
    function CreateDecoderFromFilename(Filename: String; Vendor: Cardinal; DesiredAccess: Cardinal;
      Options: Integer; out Decoder: IUnknown): HResult;
    procedure CreateDecoderFromStream;
    procedure CreateDecoderFromFileHandle;
    procedure CreateComponentInfo;
    procedure CreateDecoder;
    procedure CreateEncoder;
    procedure CreatePalette;
    function CreateFormatConverter(out Converter: IUnknown): HResult;
  end;

  TBmiHeader = record
    biSize: Cardinal;
    biWidth: Longint;
    biHeight: Longint;
    biPlanes: Word;
    biBitCount: Word;
    biCompression: Cardinal;
    biSizeImage: Cardinal;
    biXPelsPerMeter: Longint;
    biYPelsPerMeter: Longint;
    biClrUsed: Cardinal;
    biClrImportant: Cardinal;
  end;

  TPmc = record
    cb, PageFaultCount, PeakWorkingSetSize, WorkingSetSize, QuotaPeakPagedPoolUsage,
    QuotaPagedPoolUsage, QuotaPeakNonPagedPoolUsage, QuotaNonPagedPoolUsage,
    PagefileUsage, PeakPagefileUsage: Cardinal;
  end;

function CreateDIBSection(DC: Longint; var Bmi: TBmiHeader; Usage: Cardinal; var Bits: Cardinal;
  Section: Longint; Offset: Cardinal): Longint;
  external 'CreateDIBSection@gdi32.dll stdcall';
function QueryPerformanceCounter(var Count: Int64): BOOL;
  external 'QueryPerformanceCounter@kernel32.dll stdcall';
function QueryPerformanceFrequency(var Freq: Int64): BOOL;
  external 'QueryPerformanceFrequency@kernel32.dll stdcall';
function GetCurrentProcess(): Longint;
  external 'GetCurrentProcess@kernel32.dll stdcall';
function GetProcessMemoryInfo(Process: Longint; var Pmc: TPmc; Cb: Cardinal): BOOL;
  external 'K32GetProcessMemoryInfo@kernel32.dll stdcall';
function GetModuleHandle(Name: String): Longint;
  external 'GetModuleHandleW@kernel32.dll stdcall';
{ Explicit path + delayload: nothing is extracted or loaded until the first call. }
function WebpLoad(Path: String): Longint;
  external 'WebpLoad@{tmp}\otzwebp.dll stdcall delayload';

var
  Factory: IWICImagingFactory;
  Freq: Int64;
  Report, OutDir: String;

function NowUs(): Int64;
var
  C: Int64;
begin
  QueryPerformanceCounter(C);
  Result := C * 1000000 div Freq;
end;

procedure Say(const S: String);
begin
  Report := Report + S + #13#10;
  Log('HARNESS ' + S);
end;

function PrivMb(): String;
var
  P: TPmc;
begin
  P.cb := SizeOf(P);
  GetProcessMemoryInfo(GetCurrentProcess(), P, SizeOf(P));
  Result := Format('private %.1f MB, ws %.1f MB', [P.PagefileUsage / 1048576.0, P.WorkingSetSize / 1048576.0]);
end;

function Mods(): String;
begin
  Result := Format('windowscodecs=%d wmphoto=%d otzwebp=%d', [
    Ord(GetModuleHandle('windowscodecs.dll') <> 0), Ord(GetModuleHandle('wmphoto.dll') <> 0),
    Ord(GetModuleHandle('otzwebp.dll') <> 0)]);
end;

{ WIC: any in-box format -> top-down 32-bit DIB -> TBitmap. Straight=True asks WIC for straight
  BGRA and lets VCL premultiply (like TPngImage); False asks for PBGRA directly. }
function WicLoad(const FileName: String; Straight: Boolean): TBitmap;
var
  Unk: IUnknown;
  Decoder: IWICBitmapDecoder;
  Frame: IWICBitmapSource;
  Converter: IWICFormatConverter;
  Fmt: TGUID;
  W, H, Bits: Cardinal;
  Bmi: TBmiHeader;
  Dib: Longint;
begin
  OleCheck(Factory.CreateDecoderFromFilename(FileName, 0, $80000000, 0, Unk));
  Decoder := IWICBitmapDecoder(Unk);
  OleCheck(Decoder.GetFrame(0, Unk));
  Frame := IWICBitmapSource(Unk);
  OleCheck(Factory.CreateFormatConverter(Unk));
  Converter := IWICFormatConverter(Unk);
  if Straight then
    Fmt := StringToGUID(WICPixelFormat32bppBGRA)
  else
    Fmt := StringToGUID(WICPixelFormat32bppPBGRA);
  OleCheck(Converter.Initialize(Frame, Fmt, 0, 0, 0.0, 0));
  OleCheck(Converter.GetSize(W, H));
  Bmi.biSize := 40;
  Bmi.biWidth := W;
  Bmi.biHeight := -Integer(H);
  Bmi.biPlanes := 1;
  Bmi.biBitCount := 32;
  Bmi.biCompression := 0;
  Dib := CreateDIBSection(0, Bmi, 0, Bits, 0, 0);
  if (Dib = 0) or (Bits = 0) then
    RaiseException('CreateDIBSection failed');
  OleCheck(Converter.CopyPixels(0, W * 4, W * H * 4, Bits));
  Result := TBitmap.Create;
  Result.Handle := Dib;
  Result.AlphaFormat := afPremultiplied;
end;

function PngLoad(const FileName: String): TBitmap;
var
  Png: TPngImage;
begin
  Result := TBitmap.Create;
  Png := TPngImage.Create;
  try
    Png.LoadFromFile(FileName);
    Result.Assign(Png);
    if Result.AlphaFormat = afDefined then
      Result.AlphaFormat := afPremultiplied;
  finally
    Png.Free;
  end;
end;

function DllLoad(const FileName: String): TBitmap;
var
  H: Longint;
begin
  H := WebpLoad(FileName);
  if H = 0 then
    RaiseException('WebpLoad failed: ' + FileName);
  Result := TBitmap.Create;
  Result.Handle := H;
  Result.AlphaFormat := afPremultiplied;
end;

function LoadOne(Path: Integer; I: Integer): TBitmap;
var
  N: String;
begin
  N := Format('%.2d', [I]);
  case Path of
    0: Result := PngLoad(ExpandConstant('{tmp}\P_book_') + N + '.png');
    1: Result := WicLoad(ExpandConstant('{tmp}\P_book_') + N + '.png', True);
    2: Result := WicLoad(ExpandConstant('{tmp}\A_book_') + N + '.jxr', True);
    3: Result := WicLoad(ExpandConstant('{tmp}\B_book_') + N + '.jxr', True);
    4: Result := DllLoad(ExpandConstant('{tmp}\W_book_') + N + '.webp');
  end;
end;

function InitializeSetup(): Boolean;
var
  Names: array[0..4] of String;
  Frames: array[0..23] of TBitmap;
  P, I, R: Integer;
  T0, T1, Best, Worst, TF: Int64;
  Bmp: TBitmap;
begin
  Result := False;
  QueryPerformanceFrequency(Freq);
  OutDir := ExtractFilePath(ExpandConstant('{srcexe}')) + '{#Tag}\';
  ForceDirectories(OutDir);
  Names[0] := 'PNG  TPngImage (today)';
  Names[1] := 'PNG  via WIC';
  Names[2] := 'JXR  A premul-q14 via WIC';
  Names[3] := 'JXR  B straight-q14 via WIC';
  Names[4] := 'WebP via otzwebp.dll';
  try
    Say('start: ' + PrivMb() + '; ' + Mods());
    T0 := NowUs(); ExtractTemporaryFiles('{tmp}\P_book_*.png'); Say(Format('extract PNG set: %d ms', [Integer((NowUs() - T0) div 1000)]));
    T0 := NowUs(); ExtractTemporaryFiles('{tmp}\A_book_*.jxr'); Say(Format('extract JXR A set: %d ms', [Integer((NowUs() - T0) div 1000)]));
    T0 := NowUs(); ExtractTemporaryFiles('{tmp}\B_book_*.jxr'); Say(Format('extract JXR B set: %d ms', [Integer((NowUs() - T0) div 1000)]));
    T0 := NowUs(); ExtractTemporaryFiles('{tmp}\W_book_*.webp'); Say(Format('extract WebP set: %d ms', [Integer((NowUs() - T0) div 1000)]));

    T0 := NowUs();
    Factory := IWICImagingFactory(CreateComObject(StringToGUID(CLSID_WICImagingFactory)));
    Say(Format('first CreateComObject(WICImagingFactory): %d us; %s', [Integer(NowUs() - T0), Mods()]));
    T0 := NowUs(); Bmp := WicLoad(ExpandConstant('{tmp}\A_book_12.jxr'), True);
    Say(Format('first JXR decode (loads the codec): %d us; %s', [Integer(NowUs() - T0), Mods()]));
    Bmp.SaveToFile(OutDir + 'A12_straight.bmp'); Bmp.Free;
    Bmp := WicLoad(ExpandConstant('{tmp}\A_book_12.jxr'), False);
    Bmp.SaveToFile(OutDir + 'A12_pbgra_request.bmp'); Bmp.Free;
    Bmp := WicLoad(ExpandConstant('{tmp}\B_book_12.jxr'), False);
    Bmp.SaveToFile(OutDir + 'B12_pbgra_request.bmp'); Bmp.Free;

    T0 := NowUs(); ExtractTemporaryFile('otzwebp.dll');
    T1 := NowUs(); Bmp := DllLoad(ExpandConstant('{tmp}\W_book_12.webp'));
    Say(Format('extract otzwebp.dll: %d us; first WebpLoad (LoadLibrary + decode): %d us; %s', [
      Integer(T1 - T0), Integer(NowUs() - T1), Mods()]));
    Bmp.Free;

    for P := 0 to 4 do
    begin
      { all 24 held at once: memory + correctness dump }
      T0 := NowUs();
      for I := 0 to 23 do
        Frames[I] := LoadOne(P, I);
      T1 := NowUs();
      Say(Format('%s: 24 frames held: %d ms total; %s', [Names[P], Integer((T1 - T0) div 1000), PrivMb()]));
      for I := 0 to 23 do
      begin
        Frames[I].SaveToFile(OutDir + Format('p%d_%.2d.bmp', [P, I]));
        Frames[I].Free;
      end;
    end;

    { decode-only timing, paths interleaved, best of 5 rounds per path }
    for P := 0 to 4 do
    begin
      Best := 999999999; Worst := 0;
      for R := 1 to 5 do
      begin
        T0 := NowUs();
        for I := 0 to 23 do
        begin
          TF := NowUs();
          Bmp := LoadOne(P, I);
          Bmp.Free;
          TF := NowUs() - TF;
          if TF > Worst then Worst := TF;
        end;
        T1 := NowUs() - T0;
        if T1 < Best then Best := T1;
      end;
      Say(Format('%s: best-of-5 per frame avg %d us; slowest single frame %d us', [
        Names[P], Integer(Best div 24), Integer(Worst)]));
    end;
    Say('end: ' + PrivMb() + '; ' + Mods());
  except
    Say('EXCEPTION: ' + GetExceptionMessage);
  end;
  SaveStringToFile(OutDir + 'results.txt', Report, False);
end;
