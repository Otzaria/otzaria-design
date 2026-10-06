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
OutputBaseFilename=rt_leak
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


{ V1: one variable per out-parameter, everything released explicitly before returning. }
function WicLoad1(const FileName: String): TBitmap;
var
  UDec, UFrame, UConv: IUnknown;
  Decoder: IWICBitmapDecoder;
  Frame: IWICBitmapSource;
  Converter: IWICFormatConverter;
  Fmt: TGUID;
  W, H, Bits: Cardinal;
  Bmi: TBmiHeader;
  Dib: Longint;
begin
  OleCheck(Factory.CreateDecoderFromFilename(FileName, 0, $80000000, 0, UDec));
  Decoder := IWICBitmapDecoder(UDec);
  OleCheck(Decoder.GetFrame(0, UFrame));
  Frame := IWICBitmapSource(UFrame);
  OleCheck(Factory.CreateFormatConverter(UConv));
  Converter := IWICFormatConverter(UConv);
  Fmt := StringToGUID(WICPixelFormat32bppBGRA);
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
  Converter := nil; UConv := nil;
  Frame := nil; UFrame := nil;
  Decoder := nil; UDec := nil;
  Result := TBitmap.Create;
  Result.Handle := Dib;
  Result.AlphaFormat := afPremultiplied;
end;

{ V2: like V0 (one shared variable) but cleared to nil before every out-call. }
function WicLoad2(const FileName: String): TBitmap;
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
  Unk := nil;
  OleCheck(Factory.CreateDecoderFromFilename(FileName, 0, $80000000, 0, Unk));
  Decoder := IWICBitmapDecoder(Unk);
  Unk := nil;
  OleCheck(Decoder.GetFrame(0, Unk));
  Frame := IWICBitmapSource(Unk);
  Unk := nil;
  OleCheck(Factory.CreateFormatConverter(Unk));
  Converter := IWICFormatConverter(Unk);
  Unk := nil;
  Fmt := StringToGUID(WICPixelFormat32bppBGRA);
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

function PrivBytes(): Cardinal;
var
  P: TPmc;
begin
  P.cb := SizeOf(P);
  GetProcessMemoryInfo(GetCurrentProcess(), P, SizeOf(P));
  Result := P.PagefileUsage;
end;

function InitializeSetup(): Boolean;
var
  V, I, K: Integer;
  M0: Cardinal;
  Bmp: TBitmap;
  F: String;
begin
  Result := False;
  QueryPerformanceFrequency(Freq);
  OutDir := ExtractFilePath(ExpandConstant('{srcexe}')) + '{#Tag}\';
  ForceDirectories(OutDir);
  try
    ExtractTemporaryFiles('{tmp}\A_book_*.jxr');
    ExtractTemporaryFiles('{tmp}\P_book_*.png');
    Factory := IWICImagingFactory(CreateComObject(StringToGUID(CLSID_WICImagingFactory)));
    Bmp := WicLoad1(ExpandConstant('{tmp}\A_book_00.jxr')); Bmp.Free;
    Bmp := WicLoad1(ExpandConstant('{tmp}\P_book_00.png')); Bmp.Free;
    for K := 0 to 1 do
      for V := 0 to 2 do
      begin
        M0 := PrivBytes();
        for I := 0 to 47 do
        begin
          if K = 0 then F := ExpandConstant('{tmp}\A_book_') + Format('%.2d', [I mod 24]) + '.jxr'
          else F := ExpandConstant('{tmp}\P_book_') + Format('%.2d', [I mod 24]) + '.png';
          case V of
            0: Bmp := WicLoad(F, True);
            1: Bmp := WicLoad1(F);
            2: Bmp := WicLoad2(F);
          end;
          Bmp.Free;
        end;
        Say(Format('%s V%d: 48 decode+free cycles -> private bytes grew %.1f MB', [
          ExtractFileExt(F), V, (PrivBytes() - M0) / 1048576.0]));
      end;
  except
    Say('EXCEPTION: ' + GetExceptionMessage);
  end;
  SaveStringToFile(OutDir + 'results.txt', Report, False);
end;
