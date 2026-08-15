import { ArchitectureFlow } from "./components/ArchitectureFlow";
import { ComponentReveal } from "./components/ComponentReveal";
import { CoreModes } from "./components/CoreModes";
import { Footer } from "./components/Footer";
import { HardwareStory } from "./components/HardwareStory";
import { Hero } from "./components/Hero";
import { InteractiveDemo } from "./components/InteractiveDemo";
import { Navigation } from "./components/Navigation";
import { PhysicalHardware } from "./components/PhysicalHardware";
import { TechStack } from "./components/TechStack";
import { WhyArgus } from "./components/WhyArgus";

export default function App() {
  return (
    <div className="page-shell">
      <Navigation />
      <main>
        <Hero />
        <ComponentReveal />
        <CoreModes />
        <HardwareStory />
        <ArchitectureFlow />
        <PhysicalHardware />
        <InteractiveDemo />
        <WhyArgus />
        <TechStack />
      </main>
      <Footer />
    </div>
  );
}
