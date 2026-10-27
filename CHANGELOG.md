## [0.14.0](https://github.com/principat/ha-indirect-climate-control/compare/v0.13.0...v0.14.0) (2026-10-27)

### Features

* assess units that do not work only downwards and release a room only after its replacement is active ([01864d5](https://github.com/principat/ha-indirect-climate-control/commit/01864d54e544c261ca9004827d06d1c17bbf35c4))

## [0.13.0](https://github.com/principat/ha-indirect-climate-control/compare/v0.12.0...v0.13.0) (2026-10-26)

### Features

* serve rooms continuously until their unit has cut off ([7b250de](https://github.com/principat/ha-indirect-climate-control/commit/7b250deb05716ea62e7a1a34f8b70161e1fac887))

## [0.12.0](https://github.com/principat/ha-indirect-climate-control/compare/v0.11.0...v0.12.0) (2026-10-26)

### Features

* set the limit of the room as setpoint of a served unit once ([4ebe940](https://github.com/principat/ha-indirect-climate-control/commit/4ebe940294a2150d1bbfdd68149afa0581448a52))

## [0.11.0](https://github.com/principat/ha-indirect-climate-control/compare/v0.10.0...v0.11.0) (2026-10-25)

### Features

* record the command of the control for every indoor unit ([f503958](https://github.com/principat/ha-indirect-climate-control/commit/f5039582e2cb7f5c1c3b23dfb3fe3f118c7b053c))

## [0.10.0](https://github.com/principat/ha-indirect-climate-control/compare/v0.9.0...v0.10.0) (2026-10-25)

### Features

* serve one room at a time and let the rooms take turns ([dd296a5](https://github.com/principat/ha-indirect-climate-control/commit/dd296a5448844cffb2fe915af93843863778ad72))

## [0.9.0](https://github.com/principat/ha-indirect-climate-control/compare/v0.8.0...v0.9.0) (2026-10-24)

### Features

* choose between a fixed value and an entity for the setpoint of an indoor unit ([4f38206](https://github.com/principat/ha-indirect-climate-control/commit/4f382065b1ae1b4c919ce825b7a397bc991d3433))
* load control serves the neediest room first, hands over at the limit and records the outdoor power ([f6d4a82](https://github.com/principat/ha-indirect-climate-control/commit/f6d4a823d87eb9932f056947d261b22cf4005806))

## [0.8.0](https://github.com/principat/ha-indirect-climate-control/compare/v0.7.0...v0.8.0) (2026-10-24)

### Features

* load control counts power steps from the start threshold of the indoor unit ([0c741ad](https://github.com/principat/ha-indirect-climate-control/commit/0c741ad60333aa57b77f60b56263fee7ad3f0c38))
* planned offset as a diagnostic sensor per indoor unit ([3a4fd0f](https://github.com/principat/ha-indirect-climate-control/commit/3a4fd0f2fc811863449410801066258e5c96bcbd))

## [0.7.0](https://github.com/principat/ha-indirect-climate-control/compare/v0.6.0...v0.7.0) (2026-10-24)

### Features

* change the outdoor unit power sensor and the cooling switch in the options ([1702432](https://github.com/principat/ha-indirect-climate-control/commit/17024322cc58c075802e4e76ad0b5d0559a34e07))
* load control on temperature events with the power per step learned per indoor unit ([6fb2e18](https://github.com/principat/ha-indirect-climate-control/commit/6fb2e180cf4e92c18b5b22634d36ca2ff7c78a91))

### Bug Fixes

* reconfiguring no longer reloads the entry twice ([c81d7cd](https://github.com/principat/ha-indirect-climate-control/commit/c81d7cddca92ea14149469b79942857c08b897c4))

## [0.6.0](https://github.com/principat/ha-indirect-climate-control/compare/v0.5.0...v0.6.0) (2026-10-24)

### Features

* cooling mode with an optional switch and a capacity learned from operation ([73c1dee](https://github.com/principat/ha-indirect-climate-control/commit/73c1deeb4a52061a1e672e3e9018c2ecf7da4cb8))
* mandatory power sensor of the outdoor unit ([b259647](https://github.com/principat/ha-indirect-climate-control/commit/b2596477d84b81e896d852c3d1c1e60293fe90d9))
* minimum run time of the plant and a lower start value of the capacity ([7e3003d](https://github.com/principat/ha-indirect-climate-control/commit/7e3003dad3afa1e639475a0534231ab89ea79590))
* offset band per indoor unit and an SOC relative to the setpoint ([76e9066](https://github.com/principat/ha-indirect-climate-control/commit/76e9066a3ad9ed32c40b6e1c0decb7659bc53b86))
* record the operating data of the plant and the indoor units ([4528a9a](https://github.com/principat/ha-indirect-climate-control/commit/4528a9a13ca59e37add868e5b59c31123074708e))
* temperature unit switch for the plant (Celsius default, Fahrenheit) ([380b446](https://github.com/principat/ha-indirect-climate-control/commit/380b446825dc7835e1238c06f67a33674a2d57c3))
* use the device temperature as reported, without rounding to whole degrees ([3740e03](https://github.com/principat/ha-indirect-climate-control/commit/3740e036adda13b0cebfced8bd613e9c166edaab))

### Bug Fixes

* a change made while an entry is being set up no longer leaves the control on stale rooms ([180fdaf](https://github.com/principat/ha-indirect-climate-control/commit/180fdafcd278211fd2ff23737a6e603500f2f7a1))

## [0.5.0](https://github.com/principat/ha-indirect-climate-control/compare/v0.4.0...v0.5.0) (2026-10-23)

### Features

* wait before the fallback and switch units on step by step ([11a8c38](https://github.com/principat/ha-indirect-climate-control/commit/11a8c388e46606008821665ddab4e986a9a17938))

### Bug Fixes

* window contacts of an indoor unit can be edited again ([ef1dc12](https://github.com/principat/ha-indirect-climate-control/commit/ef1dc125cdf65804ada0a8497a59b317b2873a2a))

## [0.4.0](https://github.com/principat/ha-indirect-climate-control/compare/v0.3.0...v0.4.0) (2026-10-23)

### Features

* add integration icon (outdoor unit with control badge) ([52e1c4b](https://github.com/principat/ha-indirect-climate-control/commit/52e1c4b664acdbf9c90307db565dfcb53edec566))

### Bug Fixes

* connect the planner output under Configure and correct HAEO sensor names ([9601b93](https://github.com/principat/ha-indirect-climate-control/commit/9601b93d8e465164ca6c5387e7e6c0f82f7e117c))

## [0.3.0](https://github.com/principat/ha-indirect-climate-control/compare/v0.2.0...v0.3.0) (2026-10-23)

### Features

* grouped parameters, diagnostic sensors per indoor unit, several window contacts ([12121dd](https://github.com/principat/ha-indirect-climate-control/commit/12121ddda6cb22562d163c745a2fdca750023026))
* name planner sensors after the HAEO fields and migrate stored entries ([684e91a](https://github.com/principat/ha-indirect-climate-control/commit/684e91af7c06404c575ab1f07d4db4e8f9bdba29))
* upper bound without surcharge and overload limit per indoor unit ([b8ef164](https://github.com/principat/ha-indirect-climate-control/commit/b8ef164c9a217eb121dd56a1ef4a75622c7a32d2))

## [0.2.0](https://github.com/principat/ha-indirect-climate-control/compare/v0.1.1...v0.2.0) (2026-10-22)

### Features

* setup without planner sensor and simpler installation form ([29da07b](https://github.com/principat/ha-indirect-climate-control/commit/29da07b375fb4fd190daf45cc9a006e2617c52b2))

### Bug Fixes

* describe Pmax as the normal maximum power without power stages ([3724420](https://github.com/principat/ha-indirect-climate-control/commit/372442021e2fff873ac1155a0a88713ff517989a))

## [0.1.1](https://github.com/principat/ha-indirect-climate-control/compare/v0.1.0...v0.1.1) (2026-10-22)

### Bug Fixes

* keep forecast attributes out of the recorder database ([eadfba0](https://github.com/principat/ha-indirect-climate-control/commit/eadfba050bb0d0ef11e484431f0d83fc21565a4b))

## [0.1.0](https://github.com/principat/ha-indirect-climate-control/compare/v0.0.0...v0.1.0) (2026-10-22)

### Features

* plan-following control of a multi-split air conditioner ([60160e7](https://github.com/principat/ha-indirect-climate-control/commit/60160e705bd519f960b83e2ea760296aa0fac9e1))
