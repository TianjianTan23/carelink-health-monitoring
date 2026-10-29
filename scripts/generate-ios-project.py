"""Generate a self-contained Xcode project using only the Python standard library."""
from pathlib import Path
import hashlib

root=Path(__file__).resolve().parent.parent
ios=root/'ios'
def uid(name): return hashlib.sha1(('carelink:'+name).encode()).hexdigest()[:24].upper()
def quote(value): return '"'+str(value).replace('\\','\\\\').replace('"','\\"')+'"'
objects=[]
def obj(name,body): objects.append(f'{uid(name)} = {{ {body} }};');return uid(name)
swift=sorted((ios/'CareLink').glob('*.swift'))
resources=['demo-patients.json','demo-rules.json','demo-sessions.json','carelink-config.json']
source_refs=[];source_build=[];resource_refs=[];resource_build=[]
for p in swift:
 ref=obj('ref:'+p.name,f'isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = {quote(p.name)}; sourceTree = "<group>";')
 build=obj('build:'+p.name,f'isa = PBXBuildFile; fileRef = {ref};')
 source_refs.append(ref);source_build.append(build)
for name in resources:
 ref=obj('ref:'+name,f'isa = PBXFileReference; lastKnownFileType = text.json; name = {quote(name)}; path = {quote("../shared/"+name)}; sourceTree = SOURCE_ROOT;')
 build=obj('build:'+name,f'isa = PBXBuildFile; fileRef = {ref};')
 resource_refs.append(ref);resource_build.append(build)
ref=obj('ref:assets','isa = PBXFileReference; lastKnownFileType = folder.assetcatalog; path = Assets.xcassets; sourceTree = "<group>";')
source_refs.append(ref)
resource_build.append(obj('build:assets',f'isa = PBXBuildFile; fileRef = {ref};'))
product=obj('product','isa = PBXFileReference; explicitFileType = wrapper.application; includeInIndex = 0; path = CareLink.app; sourceTree = BUILT_PRODUCTS_DIR;')
sources_group=obj('sources-group','isa = PBXGroup; children = ('+','.join(source_refs)+',); path = CareLink; sourceTree = "<group>";')
shared_group=obj('shared-group','isa = PBXGroup; children = ('+','.join(resource_refs)+',); name = Shared; sourceTree = "<group>";')
products_group=obj('products-group',f'isa = PBXGroup; children = ({product},); name = Products; sourceTree = "<group>";')
main_group=obj('main-group',f'isa = PBXGroup; children = ({sources_group},{shared_group},{products_group},); sourceTree = "<group>";')
source_phase=obj('source-phase','isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = ('+','.join(source_build)+',); runOnlyForDeploymentPostprocessing = 0;')
resource_phase=obj('resource-phase','isa = PBXResourcesBuildPhase; buildActionMask = 2147483647; files = ('+','.join(resource_build)+',); runOnlyForDeploymentPostprocessing = 0;')
framework_phase=obj('framework-phase','isa = PBXFrameworksBuildPhase; buildActionMask = 2147483647; files = (); runOnlyForDeploymentPostprocessing = 0;')
target_configs=[];project_configs=[]
for name in ['Debug','Release']:
 settings='; '.join([
  'PRODUCT_BUNDLE_IDENTIFIER = com.carelink.demo', 'PRODUCT_NAME = "$(TARGET_NAME)"',
  'IPHONEOS_DEPLOYMENT_TARGET = 17.0','SDKROOT = iphoneos',
  'SUPPORTED_PLATFORMS = "iphoneos iphonesimulator"','SUPPORTS_MACCATALYST = NO',
  'SUPPORTS_MAC_DESIGNED_FOR_IPHONE_IPAD = NO','TARGETED_DEVICE_FAMILY = 1',
  'SWIFT_VERSION = 5.0','SWIFT_STRICT_CONCURRENCY = minimal','CODE_SIGN_STYLE = Automatic',
  'ASSETCATALOG_COMPILER_GLOBAL_ACCENT_COLOR_NAME = AccentColor','GENERATE_INFOPLIST_FILE = YES','INFOPLIST_FILE = LocalNetwork.plist','INFOPLIST_KEY_CFBundleDisplayName = CareLink',
  'INFOPLIST_KEY_UIApplicationSceneManifest_Generation = YES','INFOPLIST_KEY_UILaunchScreen_Generation = YES',
  'INFOPLIST_KEY_UISupportedInterfaceOrientations_iPhone = UIInterfaceOrientationPortrait',
  'CURRENT_PROJECT_VERSION = 1','MARKETING_VERSION = 1.0',
  'LD_RUNPATH_SEARCH_PATHS = "$(inherited) @executable_path/Frameworks"',
  'SWIFT_OPTIMIZATION_LEVEL = '+('"-Onone"' if name=='Debug' else '"-O"'),
 ])+';'
 target_configs.append(obj('target:'+name,f'isa = XCBuildConfiguration; buildSettings = {{ {settings} }}; name = {name};'))
 project_configs.append(obj('project:'+name,f'isa = XCBuildConfiguration; buildSettings = {{ CLANG_ENABLE_MODULES = YES; CLANG_ENABLE_OBJC_ARC = YES; }}; name = {name};'))
target_list=obj('target-list','isa = XCConfigurationList; buildConfigurations = ('+','.join(target_configs)+',); defaultConfigurationIsVisible = 0; defaultConfigurationName = Release;')
project_list=obj('project-list','isa = XCConfigurationList; buildConfigurations = ('+','.join(project_configs)+',); defaultConfigurationIsVisible = 0; defaultConfigurationName = Release;')
target=obj('target',f'isa = PBXNativeTarget; buildConfigurationList = {target_list}; buildPhases = ({source_phase},{framework_phase},{resource_phase},); buildRules = (); dependencies = (); name = CareLink; productName = CareLink; productReference = {product}; productType = "com.apple.product-type.application";')
project=obj('project',f'isa = PBXProject; attributes = {{ BuildIndependentTargetsInParallel = YES; LastUpgradeCheck = 1500; TargetAttributes = {{ {target} = {{ CreatedOnToolsVersion = 15.0; }}; }}; }}; buildConfigurationList = {project_list}; compatibilityVersion = "Xcode 14.0"; developmentRegion = en; hasScannedForEncodings = 0; knownRegions = (en, "zh-Hans", Base,); mainGroup = {main_group}; productRefGroup = {products_group}; projectDirPath = ""; projectRoot = ""; targets = ({target},);')
project_dir=ios/'CareLink.xcodeproj';project_dir.mkdir(exist_ok=True)
(project_dir/'project.pbxproj').write_text('// !$*UTF8*$!\n{ archiveVersion = 1; classes = {}; objectVersion = 56; objects = {\n'+'\n'.join(objects)+f'\n}}; rootObject = {project}; }}\n')
schemes=project_dir/'xcshareddata/xcschemes';schemes.mkdir(parents=True,exist_ok=True)
ref=f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{target}" BuildableName="CareLink.app" BlueprintName="CareLink" ReferencedContainer="container:CareLink.xcodeproj"/>'
(schemes/'CareLink.xcscheme').write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="1500" version="1.3">
 <BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries><BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">{ref}</BuildActionEntry></BuildActionEntries></BuildAction>
 <LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" debugServiceExtension="internal" allowLocationSimulation="YES"><BuildableProductRunnable runnableDebuggingMode="0">{ref}</BuildableProductRunnable></LaunchAction>
 <ProfileAction buildConfiguration="Release" shouldUseLaunchSchemeArgsEnv="YES" savedToolIdentifier="" useCustomWorkingDirectory="NO" debugDocumentVersioning="YES"><BuildableProductRunnable runnableDebuggingMode="0">{ref}</BuildableProductRunnable></ProfileAction>
 <AnalyzeAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/>
</Scheme>
''')
print('Generated CareLink.xcodeproj with',len(swift),'Swift files and',len(resources),'shared resources.')
