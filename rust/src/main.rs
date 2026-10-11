//! Portable, dependency-free DCP-T230 PJL/PWG filter.
use std::collections::HashMap;
use std::fs::{self, File, OpenOptions};
use std::io::{self, BufRead, BufReader, BufWriter, Read, Seek, SeekFrom, Write};
use std::path::PathBuf;
use std::process::{Command, Stdio};
#[cfg(unix)]
use std::os::unix::fs::DirBuilderExt;

const UEL: &[u8] = b"\x1b%-12345X";
mod cache;
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

fn paper(name: &str) -> Result<(&'static str, u32, u32, u32)> {
    Ok(match name {
        "A4" => ("A4", 2480, 3507, 9),
        "Letter" => ("LETTER", 2550, 3300, 1),
        "Legal" => ("LEGAL", 2550, 4200, 5),
        "A5" => ("A5", 1748, 2480, 11),
        "A6" => ("A6", 1236, 1748, 70),
        _ => return Err(format!("Unsupported PageSize: {name}").into()),
    })
}

fn options(text: &str) -> Result<HashMap<String, String>> {
    let mut tokens = Vec::new();
    let mut token = String::new();
    let mut quote = None;
    let mut chars = text.chars().peekable();
    while let Some(c) = chars.next() {
        match (quote, c) {
            (Some(q), c) if c == q => quote = None,
            (Some('\''), c) => token.push(c),
            (Some('"'), '\\') => {
                let next = chars.next().ok_or("Incomplete escape")?;
                if next != '"' && next != '\\' { token.push('\\'); }
                token.push(next);
            }
            (Some(_), c) => token.push(c),
            (None, '\'' | '"') => quote = Some(c),
            (None, '\\') => token.push(chars.next().ok_or("Incomplete escape")?),
            (None, c) if c.is_ascii_whitespace() => {
                if !token.is_empty() { tokens.push(std::mem::take(&mut token)); }
            }
            (None, c) => token.push(c),
        }
    }
    if quote.is_some() { return Err("Unclosed quote".into()); }
    if !token.is_empty() { tokens.push(token); }
    Ok(tokens.into_iter().filter_map(|t| {
        t.split_once('=').map(|(k,v)| (k.to_owned(),v.to_owned()))
    }).collect())
}

fn value<'a>(opts: &'a HashMap<String,String>, key: &str, default: &'a str) -> &'a str {
    opts.get(key).map(String::as_str).unwrap_or(default)
}

fn preamble(opts: &HashMap<String,String>) -> Result<Vec<u8>> {
    let mono = match value(opts,"BRMonoColor","FullColor") { "FullColor" => false, "Mono" => true, _ => return Err("Unsupported color mode".into()) };
    let render = if mono { "GRAYSCALE" } else { "COLOR" };
    if value(opts,"BRInputSlot","AutoSelect") != "AutoSelect" {
        return Err("This version supports automatic tray selection only".into());
    }
    if value(opts,"Duplex","None") != "None" {
        return Err("DCP-T230 supports simplex only".into());
    }
    let (paper,_,_,paper_code) = paper(value(opts,"PageSize","A4"))?;
    let (quality,quality_code) = match value(opts,"BRResolution","Normal") {
        "Draft" => ("DRAFT",1), "Normal" => ("NORMAL",2), "Fine" => ("HIGH",3),
        _ => return Err("Unsupported quality".into()),
    };
    let (media,media_code) = match value(opts,"BRMediaType","Plain") {
        "Plain" => ("REGULAR",1), "Inkjet" => ("INKJET",261),
        "Glossy" => ("GLOSSY",263), "Recycled" => ("RECYCLED",9),
        _ => return Err("Unsupported media".into()),
    };
    let id = format!("I000403611{:04X}{:04X}{:04X}{:04X}{:04X}{:04X}{:04X}",
                     0,media_code,quality_code,paper_code,if mono {1} else {2},0,7);
    let body = format!("@PJL \n@PJL SET HOLD=OFF\n@PJL SET STRINGCODESET=UTF8\n\
@PJL SET PAPER={paper}\n@PJL SET BORDERLESS=OFF\n\
@PJL SET JTTOPMARGIN=300\n@PJL SET JTBOTMARGIN=300\n\
@PJL SET JTLEFTMARGIN=300\n@PJL SET JTRIGHTMARGIN=300\n\
@PJL SET RENDERMODE={render}\n@PJL SET PRINTQUALITY={quality}\n\
@PJL SET DUPLEX=OFF\n@PJL SET MEDIATYPE={media}\n\
@PJL SET MANUALFEED=OFF\n@PJL SET SOURCETRAY=AUTO\n\
@PJL JOBSETTINGLOG DRIVER={id}\n@PJL SET FIDELITY=TRUE\n\
@PJL ENTER LANGUAGE=PWGRASTER\n");
    let mut out = UEL.to_vec(); out.extend_from_slice(body.as_bytes()); Ok(out)
}

fn header(width: u32, height: u32, channels: u32) -> [u8;1796] {
    let mut h = [0u8;1796];
    h[..9].copy_from_slice(b"PwgRaster"); h[128..132].copy_from_slice(b"auto");
    for (offset,value) in [(276,300),(280,300),(352,(width*72+150)/300),
        (356,(height*72+150)/300),(372,width),(376,height),(384,8),(388,channels*8),
        (392,width*channels),(400,if channels==1 {18} else {19}),(420,channels)] {
        h[offset..offset+4].copy_from_slice(&value.to_be_bytes());
    }
    h
}

fn encode_row_channels<const CHANNELS: usize>(row: &[u8], repeats: usize, out: &mut Vec<u8>) -> Result<()> {
    let channels = CHANNELS;
    if row.is_empty() || row.len()%channels != 0 || !(1..=256).contains(&repeats) {
        return Err("Invalid RGB row or repeat count".into());
    }
    out.clear(); out.push((repeats-1) as u8);
    let pixels = row.len()/channels;
    let pixel = |i: usize| &row[i*channels..(i+1)*channels];
    // Uniform scanlines (white margins and blank pages) avoid per-pixel packet scanning.
    if row.chunks_exact(channels).all(|p| p == pixel(0)) {
        let mut remaining = pixels;
        while remaining > 0 {
            let count = remaining.min(128);
            out.push((count-1) as u8); out.extend_from_slice(pixel(0)); remaining -= count;
        }
        return Ok(());
    }
    let mut i = 0;
    while i < pixels {
        let mut run = 1;
        while run < 128 && i+run < pixels && pixel(i) == pixel(i+run) { run += 1; }
        if run >= 2 {
            out.push((run-1) as u8); out.extend_from_slice(pixel(i)); i += run;
        } else {
            let start = i; i += 1;
            while i < pixels && i-start < 128 {
                if i+1 < pixels && pixel(i) == pixel(i+1) { break; }
                i += 1;
            }
            let count = i-start;
            out.push(if count == 1 { 0 } else { (257-count) as u8 });
            out.extend_from_slice(&row[start*channels..i*channels]);
        }
    }
    Ok(())
}

#[cfg(test)]
fn encode_row(row: &[u8], repeats: usize, out: &mut Vec<u8>) -> Result<()> {
    encode_row_channels::<3>(row,repeats,out)
}

fn token<R: BufRead>(src: &mut R) -> Result<Option<Vec<u8>>> {
    let mut out = Vec::new();
    let mut c = [0u8;1];
    loop {
        if src.read(&mut c)? == 0 {
            return if out.is_empty() { Ok(None) } else { Err("Truncated PPM header".into()) };
        }
        if c[0] == b'#' && out.is_empty() {
            // Consume comments without allowing an unbounded allocation.
            while src.read(&mut c)? != 0 && c[0] != b'\n' {}
        } else if b" \t\r\n".contains(&c[0]) {
            if !out.is_empty() { return Ok(Some(out)); }
        } else {
            out.push(c[0]);
            if out.len()>32 { return Err("Invalid PPM token".into()); }
        }
    }
}

fn number<R: BufRead>(src: &mut R) -> Result<u32> {
    let t = token(src)?.ok_or("Truncated PPM header")?;
    Ok(std::str::from_utf8(&t)?.parse()?)
}

fn convert_page<const CHANNELS: usize,R: BufRead,W: Write>(src:&mut R,out:&mut W,width:u32,height:u32,encoded:&mut Vec<u8>)->Result<()> {
        out.write_all(&header(width,height,CHANNELS as u32))?;
        let mut previous=vec![0u8;width as usize*CHANNELS];
        let mut row=vec![0u8;width as usize*CHANNELS];
        let mut repeats=0;
        for _ in 0..height {
            src.read_exact(&mut row).map_err(|e| format!("Truncated PPM pixels: {e}"))?;
            if repeats>0 && row==previous && repeats<256 { repeats+=1; }
            else {
                if repeats>0 { encode_row_channels::<CHANNELS>(&previous,repeats,encoded)?; out.write_all(encoded)?; }
                std::mem::swap(&mut row,&mut previous); repeats=1;
            }
        }
        encode_row_channels::<CHANNELS>(&previous,repeats,encoded)?; out.write_all(encoded)?;
    Ok(())
}

fn convert<R: BufRead,W: Write>(src: &mut R,out: &mut W) -> Result<usize> {
    let mut pages=0;
    let mut encoded=Vec::with_capacity(19000);
    while let Some(magic)=token(src)? {
        let channels = match magic.as_slice() { b"P6" => 3, b"P5" => 1, _ => return Err("Expected binary PPM or PGM".into()) };
        let width=number(src)?; let height=number(src)?; let depth=number(src)?;
        if !(1..=6000).contains(&width) || !(1..=10000).contains(&height) || depth != 255 {
            return Err("Unsupported PPM geometry/depth".into());
        }
        if pages==0 { out.write_all(b"RaS2")?; }
        if channels==3 { convert_page::<3,_,_>(src,out,width,height,&mut encoded)?; }
        else { convert_page::<1,_,_>(src,out,width,height,&mut encoded)?; }
        pages+=1;
    }
    if pages==0 { return Err("No pages rendered".into()); }
    Ok(pages)
}

struct TempDir(PathBuf);
impl TempDir {
    fn new() -> Result<Self> {
        let mut random=File::open("/dev/urandom")?;
        for _ in 0..10 {
            let mut bytes=[0u8;16];random.read_exact(&mut bytes)?;
            let name=bytes.iter().map(|b| format!("{b:02x}")).collect::<String>();
            let path=std::env::temp_dir().join(format!("dcpt230-rust-{name}"));
            let mut builder=fs::DirBuilder::new();
            #[cfg(unix)] builder.mode(0o700);
            match builder.create(&path) {
                Ok(()) => return Ok(Self(path)),
                Err(e) if e.kind()==io::ErrorKind::AlreadyExists => continue,
                Err(e) => return Err(e.into()),
            }
        }
        Err("Could not create private temporary directory".into())
    }
}
impl Drop for TempDir { fn drop(&mut self) { let _=fs::remove_dir_all(&self.0); } }

fn run(args: &[String]) -> Result<()> {
    if args.len()==2 && args[1]=="--ppm" {
        let mut out=BufWriter::with_capacity(65536,io::stdout().lock());
        convert(&mut BufReader::with_capacity(65536,io::stdin().lock()),&mut out)?;
        out.flush()?;return Ok(());
    }
    if args.len()==3 && args[1]=="--preamble" {
        io::stdout().write_all(&preamble(&options(&args[2])?)?)?;return Ok(());
    }
    if args.len()!=6 && args.len()!=7 {
        return Err("Usage: dcpt230-rust job user title copies options [file]".into());
    }
    let opts=options(&args[5])?;let envelope=preamble(&opts)?;
    let copies:usize=args[4].parse()?;
    if !(1..=999).contains(&copies) { return Err("Invalid copy count".into()); }
    let (_,width,height,_)=paper(value(&opts,"PageSize","A4"))?;
    let temp=TempDir::new()?;
    let input=temp.0.join("input");
    {
        let mut dest=File::create(&input)?;
        if args.len()==7 { io::copy(&mut File::open(&args[6])?,&mut dest)?; }
        else { io::copy(&mut io::stdin().lock(),&mut dest)?; }
    }
    let cache = cache::Cache::prepare(&opts,&input,&temp.0)?;
    let hit = cache.as_ref().and_then(|c| c.load().ok().flatten());
    let mut raster=OpenOptions::new().read(true).write(true).create_new(true).open(temp.0.join("raster"))?;
    let pages = if let Some((mut cached,pages)) = hit {
        io::copy(&mut cached,&mut raster)?;
        eprintln!("INFO: Render cache hit"); pages
    } else {
    let device=if value(&opts,"BRMonoColor","FullColor")=="Mono" { "-sDEVICE=pgmraw" } else { "-sDEVICE=ppmraw" };
    let mut child=Command::new("gs").args(["-q","-dSAFER","-dBATCH","-dNOPAUSE","-dFIXEDMEDIA",
        "-dPDFFitPage",device,"-r300"])
        .arg(format!("-g{width}x{height}"))
        .args(["-sOutputFile=-","-sstdout=%stderr","-f"]).arg(&input)
        .stdin(Stdio::null()).stdout(Stdio::piped()).spawn()?;
    let rendered={
        let stdout=child.stdout.take().ok_or("Missing Ghostscript output")?;
        let mut src=BufReader::with_capacity(65536,stdout);
        let mut out=BufWriter::with_capacity(65536,&mut raster);
        convert(&mut src,&mut out).and_then(|pages| { out.flush()?;Ok(pages) })
    };
    let pages=match rendered {
        Ok(pages) => pages,
        Err(e) => { let _=child.kill();let _=child.wait();return Err(e); }
    };
    if !child.wait()?.success() { return Err("Ghostscript failed".into()); }
    if let Some(c)=&cache {
        if let Err(e)=c.store(&mut raster,pages,&temp.0) { eprintln!("WARNING: Render cache unavailable: {e}"); }
    }
    pages
    };
    let mut out=BufWriter::with_capacity(65536,io::stdout().lock());
    for _ in 0..copies {
        out.write_all(&envelope)?;raster.seek(SeekFrom::Start(0))?;
        io::copy(&mut raster,&mut out)?;out.write_all(UEL)?;out.write_all(UEL)?;
    }
    out.flush()?;eprintln!("INFO: Rendered {pages} pages, {copies} copies");Ok(())
}

fn main() {
    if let Err(error)=run(&std::env::args().collect::<Vec<_>>()) {
        eprintln!("ERROR: {error}");std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn unpack(row: &[u8]) -> Vec<u8> {
        let mut out=Vec::new();let mut pos=1;
        while pos<row.len() {
            let control=row[pos];pos+=1;
            if control<128 {
                for _ in 0..=control { out.extend_from_slice(&row[pos..pos+3]); }
                pos+=3;
            } else {
                assert_ne!(control,128);let count=257-control as usize;
                out.extend_from_slice(&row[pos..pos+count*3]);pos+=count*3;
            }
        }
        out
    }

    #[test]
    fn packet_boundaries() {
        for width in [1,2,3,127,128,129,255,256,257,6000] {
            for repeating in [false,true] {
                let row=(0..width*3).map(|i| if repeating { 255 } else { (i%251) as u8 }).collect::<Vec<_>>();
                for repeats in [1,2,255,256] {
                    let mut encoded=Vec::new();encode_row(&row,repeats,&mut encoded).unwrap();
                    assert_eq!(encoded[0] as usize,repeats-1);assert_eq!(unpack(&encoded),row);
                }
            }
        }
    }

    #[test]
    fn bad_rows() {
        for (row,count) in [(b"".as_slice(),1),(b"a".as_slice(),1),(b"abc".as_slice(),0),(b"abc".as_slice(),257)] {
            assert!(encode_row(row,count,&mut Vec::new()).is_err());
        }
    }

    #[test]
    fn ppm_errors() {
        for bad in [b"".as_slice(),b"P6\n1 1\n255\n\0".as_slice(),
                    b"P6\n0 1\n255\n".as_slice(),b"P6\n1 1\n65535\n".as_slice()] {
            assert!(convert(&mut io::Cursor::new(bad),&mut Vec::new()).is_err());
        }
    }

    #[test]
    fn quoted_options() {
        let opts=options("PageSize='A4' BRResolution=\"Fine\" ignored title=hello\\ world").unwrap();
        assert_eq!(opts["title"],"hello world");assert_eq!(opts["BRResolution"],"Fine");
        assert!(options("PageSize='A4").is_err());
    }

    #[test]
    fn default_envelope() {
        let p=preamble(&HashMap::new()).unwrap();
        assert!(p.starts_with(UEL));assert!(p.ends_with(b"@PJL ENTER LANGUAGE=PWGRASTER\n"));
        assert!(String::from_utf8(p).unwrap().contains("I0004036110000000100020009000200000007"));
    }
}
