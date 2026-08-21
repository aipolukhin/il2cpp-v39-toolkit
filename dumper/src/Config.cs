namespace Il2CppDumper
{
    public class Config
    {
        public bool DummyDllAddToken { get; set; } = true;
        public bool RequireAnyKey { get; set; } = false;
        public bool ForceIl2CppVersion { get; set; } = false;
        public double ForceVersion { get; set; } = 0;
        public bool ForceDump { get; set; } = false;
        public bool NoRedirectedPointer { get; set; } = false;
        public bool DumpMethod { get; set; } = true;
        public bool DumpField { get; set; } = true;
        public bool DumpProperty { get; set; } = true;
        public bool DumpAttribute { get; set; } = true;
        public bool DumpFieldOffset { get; set; } = true;
        public bool DumpMethodOffset { get; set; } = true;
        public bool DumpTypeDefIndex { get; set; } = true;
        public bool GenerateDummyDll { get; set; } = true;
        public bool GenerateScript { get; set; } = false;
        public bool DumpImageBase { get; set; } = true;
    }
}
