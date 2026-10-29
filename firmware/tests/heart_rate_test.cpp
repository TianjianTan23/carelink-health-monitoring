#include "../elder_sensors/heart_rate_processor.h"
#include <cassert>
#include <iostream>

static void feed(HeartRateProcessor& p, uint32_t from, uint32_t until, float bpm,
                 float dc=2200, float amplitude=60, bool inverted=false) {
  for (uint32_t t=from; t<until; t+=2) {
    float phase=(t-from)/1000.0f*bpm/60*6.283185307f;
    float pulse=amplitude*std::sin(phase)*(inverted?-1:1);
    float light=12*std::sin(t/1000.0f*50*6.283185307f);
    p.sample(static_cast<int>(dc+pulse+light),t);
  }
}
int main() {
  int checks=0;
  for (float bpm : {40.f,60.f,75.f,110.f,150.f,190.f}) {
    for (bool inverse : {false,true}) {
      HeartRateProcessor p; feed(p,2,14002,bpm,2200,60,inverse);
      auto v=p.snapshot(14000);
      std::cout << "wave " << bpm << " inversion=" << inverse << " result=" << v.bpm << '\n';
      assert(v.valid && std::fabs(v.bpm-bpm)<4); ++checks;
    }
  }
  HeartRateProcessor lowDC; feed(lowDC,2,12002,75,1000);
  assert(lowDC.snapshot(12000).valid); ++checks;
  HeartRateProcessor step; feed(step,2,10002,75); feed(step,10002,17002,120);
  assert(std::fabs(step.snapshot(17000).bpm-120)<5); ++checks;
  HeartRateProcessor slow; feed(slow,2,10002,120); feed(slow,10002,23002,45);
  assert(std::fabs(slow.snapshot(23000).bpm-45)<4); ++checks;
  HeartRateProcessor flat; feed(flat,2,12002,0,2200,0);
  assert(!flat.snapshot(12000).valid); ++checks;
  HeartRateProcessor loss; feed(loss,2,12002,75);
  for (uint32_t t=12002;t<20002;t+=2) loss.sample(2200,t);
  auto held=loss.snapshot(20000); assert(!held.valid && held.held && std::isfinite(held.displayBpm)); ++checks;
  for (uint32_t t=20002;t<50002;t+=2) loss.sample(2200,t);
  assert(!std::isfinite(loss.snapshot(50000).displayBpm)); ++checks;
  HeartRateProcessor gap; feed(gap,2,10002,75); feed(gap,10102,22002,75);
  assert(gap.snapshot(22000).gapCount==1 && gap.snapshot(22000).valid); ++checks;
  HeartRateProcessor saturated; for(uint32_t t=2;t<5000;t+=2)saturated.sample(4095,t);
  assert(!saturated.snapshot(5000).valid); ++checks;
  std::cout << checks << " KY-039 synthetic signal checks passed\n";
}
