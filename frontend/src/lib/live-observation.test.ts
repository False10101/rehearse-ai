import assert from "node:assert/strict";
import test from "node:test";
import type { Detection, Matrix } from "@mediapipe/tasks-vision";
import { observationFromLandmarks, objectsFromDetections } from "./live-observation.ts";

function face() {
  const p = Array.from({ length: 478 }, () => ({ x: .5, y: .5, z: 0, visibility: 1 }));
  for (const [a, b, x] of [[33, 133, .35], [362, 263, .65]]) { p[a].x = x - .02; p[b].x = x + .02; }
  for (const i of [159, 386]) p[i].y = .49;
  for (const i of [145, 374]) p[i].y = .51;
  for (const i of [468, 469, 470, 471, 472]) p[i].x = .35;
  for (const i of [473, 474, 475, 476, 477]) p[i].x = .65;
  return p;
}
function matrix(yaw=0, pitch=0, roll=0): Matrix {
  const y=yaw*Math.PI/180, p=pitch*Math.PI/180, r=roll*Math.PI/180;
  return { rows:4, columns:4, data:[Math.cos(y)*Math.cos(r),Math.sin(r),-Math.sin(y),0,-Math.sin(r),Math.cos(p)*Math.cos(r),-Math.sin(p),0,Math.sin(y)*Math.cos(p),Math.sin(p),Math.cos(y)*Math.cos(p),0,0,0,-40,1] };
}
test("missing face never fabricates eye/head measurements", () => {
  const r=observationFromLandmarks(undefined); assert.equal(r.person_detected,false); assert.equal(r.eyes,undefined); assert.equal(r.head,undefined);
});
test("neutral head and iris are independent", () => {
  const r=observationFromLandmarks(face(),matrix()); assert.deepEqual(r.head,[0,0,0]);
  for(const v of r.eyes!) assert.ok(Math.abs(v-.5)<1e-6);
  for(const v of r.eye_openness!) assert.ok(Math.abs(v-.5)<1e-6);
  assert.ok(r.debug?.face && r.debug.left_eye && r.debug.right_eye);
});
for(const [side,x,y] of [["left",.008,0],["right",-.008,0],["up",0,-.004],["down",0,.004]] as const) {
  test(`eye-only ${side} with stationary head`,()=>{
    const p=face(); for(const i of [468,469,470,471,472,473,474,475,476,477]){p[i].x+=x;p[i].y+=y;}
    for(const i of [159,145,386,374])p[i].y+=y;
    const r=observationFromLandmarks(p,matrix());assert.deepEqual(r.head,[0,0,0]);
    assert.ok(Math.abs(r.eyes![x?0:1]-.5)>.1);assert.equal(Math.sign(r.eyes![x?0:1]-.5),Math.sign(x||y));
  });
}
for(const [side,yaw,pitch,roll] of [["left",25,0,0],["right",-25,0,0],["up",0,25,0],["down",0,-25,0],["lean-left",0,0,-25],["lean-right",0,0,25]] as const) {
  test(`head-only ${side} uses pose, not iris displacement`,()=>{
    const r=observationFromLandmarks(face(),matrix(yaw,pitch,roll));
    for(const [i,v] of [yaw,pitch,roll].entries()) assert.ok(Math.abs(r.head![i]-v)<1e-5);
    for(const v of r.eyes!) assert.ok(Math.abs(v-.5)<1e-6);
  });
}
test("blink rejects iris measurements without losing head pose",()=>{
  const p=face();for(const i of [159,145,386,374])p[i].y=.5;
  const r=observationFromLandmarks(p,matrix());assert.equal(r.eyes,undefined);assert.deepEqual(r.eye_openness,[0,0]);assert.ok(r.head);
});
test("body/hand packets carry explicit sampling markers",()=>{
  const r=observationFromLandmarks(face(),matrix(),face().slice(0,33),[face().slice(0,21)]);
  assert.equal(r.body?.length,33);assert.equal(r.hands?.[0].length,21);
  const skipped=observationFromLandmarks(face(),matrix(),undefined,undefined,false,false);
  assert.equal(skipped.body_updated,false);assert.equal(skipped.hands_updated,false);
});


test("object boxes are normalised and low-confidence detections are omitted", () => {
  const item = {boundingBox:{originX:250,originY:125,width:500,height:250},
    categories:[{categoryName:"cup",score:.8}]} as Detection;
  const result=objectsFromDetections([item],1000,500);
  assert.deepEqual(result,[{label:"cup",confidence:.8,bounds:{x:.25,y:.25,width:.5,height:.5}}]);
  assert.deepEqual(objectsFromDetections([{...item,categories:[{...item.categories[0],score:.2}]}],1000,500),[]);
  assert.deepEqual(objectsFromDetections([item],0,500),[]);
});
