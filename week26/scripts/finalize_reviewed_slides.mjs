import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const ROOT=process.cwd(),C=path.join(ROOT,'.cache/week26-slides');
const SKILL='/Users/shivio/.codex/plugins/cache/openai-primary-runtime/presentations/26.1022.11436/skills/presentations';
const PY='/Users/shivio/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python';
const {finalizePresentation}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
const ref=path.join(ROOT,'week24/slides/references/第24回進捗_HyperNovaとNova_環境構築_実装.pptx');
for(const [tag,name] of [['D','Week26_教授指摘反映_条件と結果_v3.pptx']]){
 const records=JSON.parse(await fs.readFile(path.join(C,tag,'slide-map.json'),'utf8'));
 const tables=records.filter(x=>x.tables).map(x=>x.slide),charts=records.filter(x=>x.charts).map(x=>x.slide);
 const result=await finalizePresentation({workspaceDir:ROOT,candidatePath:path.join(C,tag,'candidate.pptx'),finalPath:path.join(ROOT,'week26/slides',name),pythonExecutable:PY,
 integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),
 explicitTotalSlideCount:57,requiredNativeTableOwnerSlides:tables,requiredNativeChartOwnerSlides:charts,
 materializeLiteralChartWorkbooks:true,verifyArtifactToolImport:true,
 layoutArgs:['--expected-slide-size-emu','9144000,6858000','--validate-bullet-geometry','--validate-heading-fit',...tables.flatMap(n=>['--require-native-table-slide',String(n)])],
 fontPolicy:{basis:'reference',families:['Hiragino Kaku Gothic ProN W3','Hiragino Kaku Gothic ProN W6'],referencePath:ref,referenceSha256:'48f467231efab43c232f93d0dcaacf75576f296a7bbf44f3aa4465915e14e1cc'},
 receiptPath:path.join(C,tag,'validation-complete.json')});
 console.log(tag,JSON.stringify(result));
}
