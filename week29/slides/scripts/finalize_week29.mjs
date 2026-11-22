import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const skill=process.env.PRESENTATIONS_SKILL_DIR;
if(!skill) throw Error('PRESENTATIONS_SKILL_DIR is required');
const {finalizePresentation}=await import(path.join(skill,'container_tools/artifact_tool_utils.mjs'));
const manifest=JSON.parse(await fs.readFile(path.join(root,'.cache/week29-slides-build/deck-manifest.json'),'utf8'));
const ref=path.join(root,'week24/slides/references/第24回進捗_HyperNovaとNova_環境構築_実装.pptx');
const result=await finalizePresentation({
 workspaceDir:root,candidatePath:path.join(root,'.cache/week29-slides-build/candidate.pptx'),
 finalPath:path.join(root,'week29/slides/output/第29回_実験説明版.pptx'),
 pythonExecutable:process.env.RUNTIME_PYTHON,
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','9144000,6858000','--validate-bullet-geometry','--validate-heading-fit',...manifest.tableOwners.flatMap(n=>['--require-native-table-slide',String(n)])],
 requiredNativeTableOwnerSlides:manifest.tableOwners,requiredNativeChartOwnerSlides:manifest.chartOwners,
 materializeLiteralChartWorkbooks:true,
 fontPolicy:{basis:'reference',families:[manifest.font,'Hiragino Kaku Gothic ProN W6'],referencePath:ref,referenceSha256:crypto.createHash('sha256').update(await fs.readFile(ref)).digest('hex')},
 verifyArtifactToolImport:true,
 receiptPath:path.join(root,'.cache/week29-slides-build/final-validation-experiment.json'),
});
console.log(JSON.stringify({finalPath:result.finalPath,sha256:result.finalSha256,layout:result.presentationLayout.finding_count,charts:result.nativeQuantitativeCharts?.validatedSlideCount}));
