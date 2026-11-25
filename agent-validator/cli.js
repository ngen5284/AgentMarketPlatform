#!/usr/bin/env node

/**
 * [AgentMarketPlatform] 에이전트 검증 CLI 도구
 * 사용법: node agent-validator/cli.js <에이전트 폴더 경로 또는 manifest.json 경로>
 */

import fs from "fs";
import path from "path";
import { AgentValidator } from "./validator.js";

const targetPath = process.argv[2];

if (!targetPath) {
    console.log("\n사용법: node agent-validator/cli.js <에이전트_경로>");
    console.log("예시:   node agent-validator/cli.js agents/text_analyzer\n");
    process.exit(1);
}

const resolved = path.resolve(targetPath);

let manifestPath = resolved;
let agentDir = resolved;

if (fs.existsSync(resolved) && fs.statSync(resolved).isDirectory()) {
    manifestPath = path.join(resolved, "manifest.json");
    agentDir = resolved;
} else {
    agentDir = path.dirname(resolved);
}

if (!fs.existsSync(manifestPath)) {
    console.error(`\n❌ 오류: manifest.json을 찾을 수 없습니다: ${manifestPath}\n`);
    process.exit(1);
}

let manifest = {};
try {
    const raw = fs.readFileSync(manifestPath, "utf-8");
    manifest = JSON.parse(raw);
} catch (e) {
    console.error(`\n❌ 오류: manifest.json 파싱 실패: ${e.message}\n`);
    process.exit(1);
}

let code = "";
const entrypoint = manifest.entrypoint || "agent.py";
const codePath = path.join(agentDir, entrypoint);

if (fs.existsSync(codePath)) {
    code = fs.readFileSync(codePath, "utf-8");
}

console.log("\n========================================================");
console.log(`🔍 [에이전트 검증 시작] ID: ${manifest.id || "알 수 없음"}`);
console.log(`📁 검사 대상: ${agentDir}`);
console.log("========================================================\n");

const result = AgentValidator.inspect(manifest, code);

if (result.success) {
    console.log("✅ [검증 성공] 마켓플레이스 등록 및 배포 가능");
    console.log(`- 유형: ${result.structure.type}`);
    console.log(`- 위험도 등급: ${result.structure.normalizedManifest.riskLevel}`);
    console.log(`- 사람 승인 필수 여부: ${result.structure.normalizedManifest.requiresConfirmation ? "예(필수)" : "아니오"}`);
    if (result.structure.normalizedManifest.requiredTools.length > 0) {
        console.log(`- 요구 도구 목록: ${result.structure.normalizedManifest.requiredTools.join(", ")}`);
    }
} else {
    console.error(`❌ [검증 실패 - 반려] 단계: ${result.stage}`);
    console.error(`- 사유: ${result.summary}`);
}

console.log("\n========================================================\n");
process.exit(result.success ? 0 : 1);
