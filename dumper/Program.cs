using System;
using System.IO;
using System.Linq;
using System.Text;
using Il2CppDumper;

class Program {
    static void Main(string[] args) {
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
        string so=args[0], meta=args[1], outdir=args[2];
        var metadata=new Metadata(new MemoryStream(File.ReadAllBytes(meta)));
        Console.WriteLine($"Metadata v{metadata.Version}");
        var b=File.ReadAllBytes(so);
        if(!(BitConverter.ToUInt32(b,0)==0x464c457f && b[4]==2)){ Console.WriteLine("not ELF64"); return; }
        Il2Cpp il2Cpp=new Elf64(new MemoryStream(b));
        var version=metadata.Version;
        il2Cpp.SetProperties(version, metadata.metadataUsagesCount);
        Console.WriteLine($"Il2Cpp v{il2Cpp.Version}");
        bool flag=il2Cpp.CheckDump();
        if(!flag){
            flag=il2Cpp.PlusSearch(metadata.methodDefs.Count(x=>x.methodIndex>=0), metadata.typeDefs.Length, metadata.imageDefs.Length);
            Console.WriteLine($"PlusSearch: {flag}");
            if(!flag){ flag=il2Cpp.Search(); Console.WriteLine($"Search: {flag}"); }
            if(!flag){ flag=il2Cpp.SymbolSearch(); Console.WriteLine($"SymbolSearch: {flag}"); }
        }
        if(!flag){ Console.WriteLine("REGISTRATION NOT FOUND"); return; }
        if(il2Cpp.Version>=27 && il2Cpp.IsDumped){
            var td=metadata.typeDefs[0]; var t=il2Cpp.types[td.byvalTypeIndex];
            metadata.ImageBase=t.data.typeHandle - metadata.header.typeDefinitionsOffset;
        }
        var executor=new Il2CppExecutor(metadata, il2Cpp);
        Directory.CreateDirectory(outdir);
        DummyAssemblyExporter.Export(executor, outdir, false);
        // Export SetCurrentDirectory'd into <outdir>/DummyDll; count there, not top-level.
        var dummyDir = Directory.GetCurrentDirectory();
        Console.WriteLine($"DONE -> {Directory.GetFiles(dummyDir,"*.dll").Length} dlls in {dummyDir}");
    }
}
