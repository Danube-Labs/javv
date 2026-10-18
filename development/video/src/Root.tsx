import { Composition } from 'remotion'
import { makeVideo } from './engine'
import { v1 } from './videos/v1'
import { v2 } from './videos/v2'
import { v3 } from './videos/v3'
import { v4 } from './videos/v4'
import { v5 } from './videos/v5'
import { v6 } from './videos/v6'

const videos = { V1: makeVideo(v1), V2: makeVideo(v2), V3: makeVideo(v3), V4: makeVideo(v4), V5: makeVideo(v5), V6: makeVideo(v6) }

export const RemotionRoot = () => (
  <>
    {Object.entries(videos).map(([id, v]) => (
      <Composition key={id} id={id} component={v.Component} durationInFrames={v.duration} fps={30} width={1920} height={1080} />
    ))}
  </>
)
